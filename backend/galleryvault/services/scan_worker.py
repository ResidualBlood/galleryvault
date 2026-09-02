"""Library scanning, duplicate synchronization, and image quality backfill."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from starlette.concurrency import run_in_threadpool

from ..app.state import app_state
from ..config import get_settings
from ..db.repository import GalleryRepository
from ..logging import bind_log_context, log_extra
from . import messages
from .download_worker import infer_image_quality
from .ingest import GalleryIngestService
from .library import LibraryService

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

scan_lock = asyncio.Lock()


def _scan_roots() -> list[str]:
    settings = app_state.settings or get_settings()
    roots = list(settings.library_roots)
    if settings.download_root and settings.download_root not in roots:
        roots.append(settings.download_root)
    return roots


def scan_summary_message(
    last: dict[str, Any], duplicates: int, duplicate_gids: list[int], lang: str = "zh"
) -> str:
    """Human-readable scan completion message for Telegram notifications."""
    return messages.scan_summary(
        last.get("persisted", 0),
        last.get("expunged", 0),
        duplicates,
        duplicate_gids,
        lang,
    )


async def backfill_image_quality(should_stop: Callable[[], bool] | None = None) -> int:
    """Infer image_quality for local galleries missing it, fetching cold gdata batches."""
    client = app_state.eh_client
    if client is None or not app_state.session_factory:
        return 0
    processed = 0
    last_id = 0
    while True:
        if should_stop is not None and should_stop():
            break
        async with app_state.session_factory() as session:
            repo = GalleryRepository(session)
            rows = await repo.pending_image_quality_gids(200, last_id)
            if not rows:
                break
            last_id = rows[-1].id
            local = {int(row.gid): (row.storage_size, row.storage_type) for row in rows}
            have = await repo.metadata_map([int(row.gid) for row in rows])

        cold = [
            (int(row.gid), row.token)
            for row in rows
            if int(row.gid) not in have or not have[int(row.gid)].get("file_size")
        ]
        if cold:
            try:
                fetched = await client.fetch_gmetadata(cold)
                async with app_state.session_factory() as session, session.begin():
                    await GalleryRepository(session).upsert_metadata(
                        [{"gid": gid, **meta} for gid, meta in fetched.items()]
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "image quality backfill gdata round failed",
                    extra=log_extra(error=type(exc).__name__),
                )
                continue
            for gid, meta in fetched.items():
                have.setdefault(int(gid), {})["file_size"] = meta.get("file_size")

        inferred = {
            int(row.gid): quality
            for row in rows
            if int(row.gid) in have
            and (
                quality := infer_image_quality(
                    local[int(row.gid)][0],
                    have[int(row.gid)].get("file_size"),
                    local[int(row.gid)][1],
                )
            )
        }
        if inferred:
            async with app_state.session_factory() as session, session.begin():
                processed += await GalleryRepository(session).set_image_qualities(inferred)
        if len(rows) < 200:
            break
        await asyncio.sleep(0.5)
    return processed


async def run_scan() -> None:
    if not app_state.session_factory:
        return
    tm = app_state.task_manager
    scan_state = tm.scan_state if tm else {}
    settings = app_state.settings or get_settings()
    if getattr(settings, "global_paused", False):
        logger.info("scan skipped: global paused", extra=log_extra(reason="global_paused"))
        scan_state["running"] = False
        return

    with bind_log_context(worker="scan"):
        async with scan_lock:
            persisted = 0
            scanned = 0
            success = 0
            errors = 0
            scan_state["running"] = True
            scan_state["completed_at"] = None
            scan_state["started_at"] = datetime.now(UTC).isoformat()
            scan_state["scanned"] = 0
            scan_state["persisted"] = 0
            scan_state["success"] = 0
            scan_state["errors"] = 0
            scan_state["last"] = None
            if tm:
                tm.clear_cancelled("scan")
            try:
                async with app_state.session_factory() as session:
                    known = await GalleryRepository(session).existing_rows(_scan_roots())
                service = LibraryService(
                    _scan_roots(),
                    batch_size=settings.scan_batch_size,
                    existing=known,
                    duplicate_policy=settings.duplicate_policy,
                )
                iterator = service.scan_batches(should_stop=lambda: bool(tm and tm.is_cancelled("scan")))
                while True:
                    if tm and tm.is_cancelled("scan"):
                        break
                    batch = await run_in_threadpool(next, iterator, None)
                    if batch is None:
                        break
                    scanned += len(batch)
                    try:
                        async with app_state.session_factory() as session, session.begin():
                            await GalleryIngestService(session).ingest(batch)
                        persisted += len(batch)
                        success += len(batch)
                    except Exception as exc:
                        errors += len(batch)
                        logger.exception(
                            "library scan batch failed",
                            extra=log_extra(error=type(exc).__name__, message=str(exc), batch_size=len(batch)),
                        )
                    scan_state["scanned"] = scanned
                    scan_state["persisted"] = persisted
                    scan_state["success"] = success
                    scan_state["errors"] = errors

                if not (tm and tm.is_cancelled("scan")):
                    async with app_state.session_factory() as session, session.begin():
                        expunged = await GalleryRepository(session).expunge_missing(
                            _scan_roots(), service.seen_path_hashes
                        )
                    scan_state["expunged"] = expunged
                    try:
                        if service.last_duplicates:
                            async with app_state.session_factory() as session:
                                meta = await GalleryRepository(session).metadata_map(
                                    [group.gid for group in service.last_duplicates]
                                )
                                for group in service.last_duplicates:
                                    tags = (meta.get(group.gid) or {}).get("tags") or []
                                    for copy in group.all_copies():
                                        copy.tags = [
                                            {"namespace": t["namespace"], "name": t["name"]}
                                            for t in tags
                                        ]
                            async with app_state.session_factory() as session, session.begin():
                                await GalleryRepository(session).sync_duplicates(
                                    service.last_duplicates
                                )
                        else:
                            async with app_state.session_factory() as session, session.begin():
                                await GalleryRepository(session).sync_duplicates([])
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "duplicate sync failed", extra=log_extra(error=type(exc).__name__)
                        )
                    scan_state["duplicates"] = len(service.last_duplicates)
                    scan_state["duplicate_gids"] = [group.gid for group in service.last_duplicates]

                    if settings.auto_sync_tags:
                        from .tag_sync_worker import enqueue_tag_sync
                        try:
                            async with app_state.session_factory() as session:
                                last_id = 0
                                while True:
                                    ids = await GalleryRepository(session).pending_tag_sync_ids(
                                        1000, last_id
                                    )
                                    if not ids:
                                        break
                                    await enqueue_tag_sync(ids)
                                    last_id = ids[-1]
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "tag sync enqueue failed", extra=log_extra(error=type(exc).__name__)
                            )

                    try:
                        quality_done = await backfill_image_quality(
                            should_stop=lambda: bool(tm and tm.is_cancelled("scan"))
                        )
                        if quality_done:
                            scan_state["image_quality_backfilled"] = quality_done
                            logger.info("image quality backfilled", extra=log_extra(count=quality_done))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "image quality backfill failed", extra=log_extra(error=type(exc).__name__)
                        )

                    counters = service.last_counters
                    scan_state["last"] = {
                        **counters.__dict__,
                        "persisted": persisted,
                        "expunged": expunged,
                    }
                    logger.info("library scan persisted", extra=log_extra(**scan_state["last"]))
            except Exception as exc:
                scan_state["last"] = {"error": type(exc).__name__, "persisted": persisted}
                logger.exception(
                    "library scan persistence error",
                    extra=log_extra(error=type(exc).__name__, message=str(exc)),
                )
            finally:
                cancelled = bool(tm and tm.is_cancelled("scan"))
                last = scan_state.get("last") or {}
                scan_state["running"] = False
                scan_state["completed_at"] = datetime.now(UTC).isoformat()
                if tm:
                    tm.record_task(
                        "scan",
                        scan_state.get("started_at"),
                        scan_state["completed_at"],
                        "cancelled" if cancelled else ("failed" if last.get("error") else "success"),
                        reason="cancelled" if cancelled else last.get("error", ""),
                        done=scanned,
                        total=0,
                    )
                    tm.clear_cancelled("scan")
                    from ..app.dependencies import spawn_task

                    spawn_task(tm.persist_history(), "persist task history")

                try:
                    if not cancelled and app_state.telegram is not None and settings.telegram_chat_ids:
                        if last.get("error"):
                            await app_state.telegram.send_message(
                                messages.scan_failed(last["error"], settings.telegram_notify_lang)
                            )
                        else:
                            await app_state.telegram.send_message(
                                scan_summary_message(
                                    last,
                                    int(scan_state.get("duplicates") or 0),
                                    list(scan_state.get("duplicate_gids") or []),
                                    settings.telegram_notify_lang,
                                )
                            )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("scan notification failed", extra=log_extra(error=type(exc).__name__))
