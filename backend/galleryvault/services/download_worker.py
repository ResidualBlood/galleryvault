"""Background worker loops and post-processing for downloads."""

from __future__ import annotations

import asyncio
import logging
import os
import time as _time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..app.state import app_state
from ..config import get_settings
from ..db.models import DownloadTask as DownloadTaskModel
from ..db.models import Gallery, GalleryUpdate
from ..db.repository import DownloadRepository
from ..logging import bind_log_context, log_extra
from ..scanners import registry
from ..scanners.base import GalleryMeta, PageInfo
from ..scanners.ehviewer import IMAGE_EXTENSIONS, natural_key
from .deletion import (
    collapse_same_stem_pages,
    prune_merged_stale_pages,
    remove_superseded_copy,
)
from .downloader import (
    ArchiveNotRetryableError,
    DownloadCancelledError,
    DownloadTask,
)
from .eh_client import (  # noqa: F401  # kept for backoff classification docs
    EhChallengeError,
    EhClientError,
    GalleryGoneError,
    GalleryReplacedError,
)
from .ingest import GalleryIngestService
from .messages import GONE_DETAIL, HOPS_DETAIL

logger = logging.getLogger(__name__)

_RETRY_BACKOFFS = (
    30, 120, 480, 1800, 3600, 7200, 10800, 14400, 18000, 21600,
)
_PROGRESS_FLUSH_STEP = 20
_PROGRESS_FLUSH_INTERVAL = 5.0
_DOWNLOAD_RETRY_SWEEP_INTERVAL = 60.0
_TELEGRAM_FLUSH_INTERVAL = 60.0

_task_event: asyncio.Event | None = None
_worker_tasks: list[asyncio.Task] = []
_target_download_concurrency: int = 2


def _get_background_session_factory() -> Any:
    return getattr(app_state, "background_session_factory", None) or app_state.session_factory


def notify_new_task() -> None:
    """Wake up download workers when a new task is enqueued or retried."""
    if _task_event is not None:
        _task_event.set()


def retry_backoff(retry_count: int) -> int:
    """Return the backoff delay (seconds) for the given failed attempt count."""
    return _RETRY_BACKOFFS[min(max(1, retry_count) - 1, len(_RETRY_BACKOFFS) - 1)]


def infer_image_quality(
    storage_size: int | None, original_size: int | None, storage_type: str | None = None
) -> str | None:
    """Infer original/resample from local size vs the ExHentai original size."""
    if not storage_size or not original_size:
        return None
    threshold = 0.8 if storage_type == "cbz" else 0.85
    return "original" if (storage_size / original_size) >= threshold else "resample"


async def ingest_downloaded_gallery(result: Any) -> None:
    """Ingest a freshly downloaded gallery directly from memory metadata."""
    try:
        path = Path(result.path)
        reg = registry
        scanner = reg.for_path(path)
        if scanner is None:
            logger.warning("download ingest: no scanner for path", extra=log_extra(path=str(path)))
            return

        if getattr(result, "quality", None) == "original":
            await asyncio.to_thread(
                prune_merged_stale_pages, path, getattr(result, "new_files", ())
            )
        await asyncio.to_thread(collapse_same_stem_pages, path)

        def _gather_pages(p: Path) -> list[PageInfo]:
            files = sorted(
                (
                    item
                    for item in p.iterdir()
                    if item.is_file()
                    and not item.name.startswith(".")
                    and item.suffix.casefold() in IMAGE_EXTENSIONS
                ),
                key=lambda item: natural_key(item.name),
            )
            return [
                PageInfo(
                    i,
                    item.name,
                    item.suffix.casefold().lstrip("."),
                    item.stat().st_size,
                    item.stat().st_mtime_ns,
                )
                for i, item in enumerate(files)
            ]

        pages = await asyncio.to_thread(_gather_pages, path)
        raw_tags = getattr(result, "tags", None) or ()
        if isinstance(raw_tags, dict):
            tags = [
                {"namespace": ns, "name": name}
                for ns, names in raw_tags.items()
                for name in (names if isinstance(names, (list, tuple, set)) else [names])
            ]
        elif isinstance(raw_tags, (list, tuple)):
            tags = []
            for item in raw_tags:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    tags.append({"namespace": str(item[0]), "name": str(item[1])})
                elif isinstance(item, dict):
                    tags.append({
                        "namespace": str(item.get("namespace", "misc")),
                        "name": str(item.get("name", "")),
                    })
                elif isinstance(item, str):
                    tags.append({"namespace": "misc", "name": item})
        else:
            tags = []
        quality = getattr(result, "quality", None)
        if quality is None:
            storage_size = sum(p.size for p in pages)
            st_type = getattr(scanner, "storage_type", getattr(scanner, "kind", lambda: "ehviewer_dir")())
            quality = infer_image_quality(
                storage_size, getattr(result, "file_size", None), st_type
            )

        sig = scanner.storage_signature(path) if hasattr(scanner, "storage_signature") else "sig"
        mtime = path.stat().st_mtime_ns if path.exists() else 0
        gallery_meta = GalleryMeta(
            title=result.title or path.name,
            path=path,
            storage_type=getattr(scanner, "storage_type", "ehviewer_dir"),
            pages=pages,
            gid=result.gid,
            token=result.token,
            title_jpn=getattr(result, "title_jpn", None),
            category=getattr(result, "category", "other"),
            uploader=getattr(result, "uploader", None),
            file_count=len(pages),
            file_size=sum(p.size or 0 for p in pages),
            rating=getattr(result, "rating", None),
            tags=tags,
            image_quality=quality,
            storage_signature=sig,
            storage_mtime_ns=mtime,
            storage_size=sum(p.size or 0 for p in pages),
            source_meta={"title": result.title or path.name, "tags": tags},
        )

        ingest_cls = GalleryIngestService
        remove_fn = remove_superseded_copy
        session_cm = _get_background_session_factory()
        old_copy: tuple[Path, int] | None = None

        if session_cm is not None:
            async with session_cm() as session, session.begin():
                if getattr(gallery_meta, "gid", None) is not None:
                    prev = await session.scalar(
                        select(Gallery).where(Gallery.gid == gallery_meta.gid)
                    )
                    if prev is not None and prev.storage_path != str(path):
                        old_copy = (Path(prev.storage_path), getattr(prev, "page_count", 0) or 0)
                await ingest_cls(session).ingest([gallery_meta])

        if getattr(result, "quality", None) == "original" and old_copy is not None:
            await remove_fn(result, old_copy[0], old_copy[1])

        logger.info("download ingest succeeded", extra=log_extra(gid=result.gid, path=str(path)))
        try:
            from .updates_worker import finalize_updates_for_new_gid

            await finalize_updates_for_new_gid(int(result.gid))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "gallery update finalize after ingest failed",
                extra=log_extra(gid=getattr(result, "gid", None), error=type(exc).__name__),
            )
        try:
            settings = app_state.settings or get_settings()
            auto_archive = bool(getattr(settings, "auto_archive_downloads", True))
            from .cold_archive import resolve_archive_roots

            has_archive = bool(resolve_archive_roots())
            if auto_archive and has_archive and getattr(result, "gid", None) is not None:
                gid_int = int(result.gid)
                if session_cm is not None:
                    try:
                        async with session_cm() as session, session.begin():
                            await DownloadRepository(session).update_archive_status(
                                gid_int, "pending", None
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Failed to pre-mark download task archive_status=pending",
                            extra=log_extra(gid=gid_int, error=type(exc).__name__),
                        )
                from ..app.dependencies import spawn_task

                spawn_task(
                    _archive_downloaded_gallery(gid_int),
                    f"download auto archive {gid_int}",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "download auto archive hook failed",
                extra=log_extra(gid=getattr(result, "gid", None), error=type(exc).__name__),
            )
    except Exception as exc:
        logger.exception(
            "download ingest failed",
            extra=log_extra(gid=getattr(result, "gid", None), error=type(exc).__name__, message=str(exc)),
        )


async def _archive_downloaded_gallery(gid: int) -> None:
    """Background task to archive a freshly ingested gallery into cold storage."""
    session_cm = _get_background_session_factory()
    if session_cm is None:
        return

    try:
        async with session_cm() as session, session.begin():
            await DownloadRepository(session).update_archive_status(gid, "pending", None)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to mark download task archive pending",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )

    archive_err: str | None = None
    dest = None
    try:
        from . import cold_archive

        dest = await cold_archive.archive_one(gid, session_factory=session_cm)
        if dest is None:
            archive_err = "archive destination not created or skipped"
    except Exception as exc:  # noqa: BLE001
        archive_err = str(exc)
        logger.warning(
            "Auto archive execution failed",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )

    try:
        async with session_cm() as session, session.begin():
            if dest is not None:
                await DownloadRepository(session).update_archive_status(gid, "ok", None)
            else:
                await DownloadRepository(session).update_archive_status(gid, "fail", archive_err)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to persist download task archive outcome",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )

    title = str(gid)
    try:
        async with session_cm() as session:
            g_row = await session.execute(
                select(Gallery.title).where(Gallery.gid == gid)
            )
            g_title = g_row.scalar_one_or_none()
            if g_title:
                title = g_title
            else:
                d_row = await session.execute(
                    select(DownloadTaskModel.title).where(DownloadTaskModel.gid == gid)
                )
                d_title = d_row.scalar_one_or_none()
                if d_title:
                    title = d_title
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to resolve gallery title for archive notification: %s", exc)

    kind = "archive_ok" if dest is not None else "archive_fail"
    detail = None if dest is not None else archive_err
    await record_archive_notification(kind, title, detail)


def maybe_scan_after_download(result: Any) -> None:
    """Ingest just the single downloaded gallery unless full scan is running."""
    tm = app_state.task_manager
    if tm and tm.scan_state.get("running"):
        return
    from ..app.dependencies import spawn_task
    spawn_task(ingest_downloaded_gallery(result), "download ingest")


async def download_progress(
    task_id: int | None,
    current_page: int,
    total_pages: int,
    archive_fallback: bool | None = None,
    gid: int | None = None,
) -> None:
    session_factory = _get_background_session_factory()
    if task_id is None or not session_factory:
        return
    try:
        async def _persist() -> None:
            async with session_factory() as session, session.begin():
                await DownloadRepository(session).progress(
                    task_id, current_page, total_pages, archive_fallback=archive_fallback
                )

        await asyncio.wait_for(_persist(), timeout=2.0)
    except TimeoutError:
        logger.warning(
            "download progress persistence timed out, skipping [task_id=%s gid=%s]",
            task_id,
            gid,
            extra=log_extra(task_id=task_id, gid=gid),
        )
    except SQLAlchemyError as exc:
        logger.warning(
            "download progress persistence failed",
            extra=log_extra(task_id=task_id, error=type(exc).__name__),
        )


async def record_download_notification(
    kind: str, title: str, detail: str | None = None
) -> None:
    notifier = app_state.telegram
    if notifier is None:
        return
    await notifier.record_download_outcome(kind, title, detail)
    settings = app_state.settings or get_settings()
    if settings.telegram_notify_level != "summary" or not notifier.pending_events:
        return
    session_factory = _get_background_session_factory()
    if not session_factory:
        return
    try:
        async with session_factory() as session:
            active = await DownloadRepository(session).count_active()
        if active == 0:
            await notifier.flush_summary()
    except SQLAlchemyError as exc:
        logger.warning(
            "telegram summary flush check failed", extra=log_extra(error=type(exc).__name__)
        )


async def record_archive_notification(
    kind: str, title: str, detail: str | None = None
) -> None:
    from .notifications import notify_archive

    notify_archive(kind, title, detail)
    notifier = app_state.telegram
    if notifier is None:
        return
    await notifier.record_archive_outcome(kind, title, detail, ring=False)
    settings = app_state.settings or get_settings()
    if (
        getattr(settings, "telegram_notify_level", "summary") != "summary"
        or not notifier.pending_archive_events
    ):
        return
    session_factory = _get_background_session_factory()
    if not session_factory:
        return
    try:
        async with session_factory() as session:
            active = await DownloadRepository(session).count_active()
        tm = app_state.task_manager
        archive_running = bool(tm.archive_state.get("running")) if tm else False
        if active == 0 and not archive_running:
            await notifier.flush_archive_summary()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "telegram archive summary flush check failed",
            extra=log_extra(error=type(exc).__name__),
        )


async def telegram_flush_loop() -> None:
    while True:
        await asyncio.sleep(_TELEGRAM_FLUSH_INTERVAL)
        notifier = app_state.telegram
        if notifier is not None:
            try:
                if notifier.events_stale(_TELEGRAM_FLUSH_INTERVAL):
                    await notifier.flush_summary()
                if hasattr(notifier, "archive_events_stale") and notifier.archive_events_stale(
                    _TELEGRAM_FLUSH_INTERVAL
                ):
                    await notifier.flush_archive_summary()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "telegram summary flush failed",
                    extra=log_extra(error=str(exc) or type(exc).__name__),
                )


def is_download_cancelled(task_id: int | None) -> bool:
    if task_id is None:
        return False
    tm = app_state.task_manager
    return bool(tm and tm.is_cancelled(task_id))


def clear_download_cancelled(task_id: int | None) -> None:
    if task_id is None:
        return
    tm = app_state.task_manager
    if tm:
        tm.clear_cancelled(task_id)


def mark_download_cancelled(task_id: int | None) -> None:
    if task_id is None:
        return
    tm = app_state.task_manager
    if tm:
        tm.request_cancel(task_id)


async def run_download(task: DownloadTask) -> None:
    if task.id is None:
        logger.warning("download task missing id; skipping", extra=log_extra(gid=task.gid))
        return
    with bind_log_context(worker="download", task_id=task.id, gid=task.gid):
        await _run_download_inner(task)


async def _apply_replacement(task: DownloadTask, exc: GalleryReplacedError) -> DownloadTask | None:
    session_cm = _get_background_session_factory()
    if session_cm is None or task.id is None:
        return None
    from .download_prepare import _local_gids

    local = await _local_gids([exc.new_gid])
    if exc.new_gid in local:
        logger.info(
            "download retarget skipped; newer gid already in library",
            extra=log_extra(gid=task.gid, new_gid=exc.new_gid),
        )
        try:
            async with session_cm() as session, session.begin():
                await DownloadRepository(session).cancel(task.id)
        except SQLAlchemyError:
            pass
        return None
    ok = False
    try:
        async with session_cm() as session, session.begin():
            ok = await DownloadRepository(session).retarget(
                task.id, exc.new_gid, exc.new_token, exc.title, exc.title_jpn
            )
    except IntegrityError:
        ok = False
    if not ok:
        logger.info(
            "download retarget skipped; newer gid already queued",
            extra=log_extra(gid=task.gid, new_gid=exc.new_gid),
        )
        return None
    settings = app_state.settings or get_settings()
    try:
        temp = Path(settings.download_root) / f".gv-{task.gid}"
        if temp.exists():
            import shutil

            from .storage_usage import safe_stat_size, storage_tracker

            sz = safe_stat_size(temp)
            shutil.rmtree(temp, ignore_errors=True)
            if sz > 0:
                storage_tracker.record_download_delta(-sz)
    except OSError:
        pass
    title = exc.title or str(exc.new_gid)
    tm = app_state.task_manager
    if tm:
        now = datetime.now(UTC).isoformat()
        tm.record_task(
            "download-updated",
            now,
            now,
            "success",
            reason=f"gid {exc.old_gid} -> {exc.new_gid}",
            done=1,
            total=1,
        )
    return DownloadTask(
        exc.new_gid,
        exc.new_token,
        title,
        task.id,
        task.max_retries,
        task.mode,
        task.category,
        max_pages=task.max_pages,
        quality=task.quality,
    )


def _extract_http_meta(exc: BaseException) -> dict[str, Any]:
    resp = getattr(exc, "response", None)
    if resp is None:
        return {}
    meta: dict[str, Any] = {}
    status_code = getattr(resp, "status_code", None)
    if status_code is not None:
        meta["status_code"] = status_code
    headers = getattr(resp, "headers", None)
    if headers and hasattr(headers, "items"):
        summary = {
            str(k): str(v)
            for k, v in headers.items()
            if str(k).lower() in {"location", "server", "cf-ray", "content-type", "retry-after"}
        }
        if summary:
            meta["headers"] = summary
    return meta


_CHALLENGE_PROBE_INTERVAL = float(os.getenv("GV_CHALLENGE_PROBE_INTERVAL", "600"))
_challenge_lock = asyncio.Lock()
_last_resume_time = 0.0
_RESUME_DEBOUNCE_SECONDS = float(os.getenv("GV_RESUME_DEBOUNCE_SECONDS", "1.0"))


async def _trigger_challenge_pause(
    sample_path: str | None = None,
    *,
    task_id: int | None = None,
    gid: int | None = None,
    response_meta: dict[str, Any] | None = None,
) -> None:
    """Trigger global pause due to ExHentai 302 anti-abuse challenge."""
    async with _challenge_lock:
        if app_state.extra.get("auto_resume_challenge") and getattr(
            app_state.settings or get_settings(), "global_paused", False
        ):
            if sample_path and not app_state.extra.get("challenge_sample_path"):
                app_state.extra["challenge_sample_path"] = sample_path
            return
        app_state.extra["auto_resume_challenge"] = True
        if sample_path:
            app_state.extra["challenge_sample_path"] = sample_path

        from .settings_service import update_runtime_settings

        update_runtime_settings({"global_paused": True})

        session_factory = _get_background_session_factory()
        if session_factory:
            try:
                from ..db.repository import SettingsRepository

                async with session_factory() as session, session.begin():
                    existing = await SettingsRepository(session).get()
                    merged = {**existing, "global_paused": True}
                    await SettingsRepository(session).save(merged)
            except Exception as exc:
                err_extra: dict[str, Any] = {"error": str(exc)}
                if task_id is not None:
                    err_extra["task_id"] = task_id
                if gid is not None:
                    err_extra["gid"] = gid
                if response_meta:
                    err_extra.update(response_meta)
                logger.exception(
                    "failed to persist global_paused setting on challenge",
                    extra=log_extra(**err_extra),
                )

        if app_state.telegram is not None:
            try:
                await app_state.telegram.send_message("🚨 触发 302 临时挑战，系统自动暂停下载")
            except Exception as exc:  # noqa: BLE001
                alert_extra: dict[str, Any] = {"error": type(exc).__name__}
                if task_id is not None:
                    alert_extra["task_id"] = task_id
                if gid is not None:
                    alert_extra["gid"] = gid
                logger.warning(
                    "failed to send challenge telegram alert",
                    extra=log_extra(**alert_extra),
                )


async def _resume_challenge_pause() -> None:
    """Resume global pause after ExHentai 302 anti-abuse challenge clears."""
    global _last_resume_time
    async with _challenge_lock:
        if not app_state.extra.get("auto_resume_challenge") and not getattr(
            app_state.settings or get_settings(), "global_paused", False
        ):
            return
        now_ts = _time.monotonic()
        if now_ts - _last_resume_time < _RESUME_DEBOUNCE_SECONDS and not app_state.extra.get("auto_resume_challenge"):
            return
        _last_resume_time = now_ts
        app_state.extra["auto_resume_challenge"] = False
        app_state.extra.pop("challenge_sample_path", None)

        from .settings_service import update_runtime_settings

        update_runtime_settings({"global_paused": False})

        session_factory = _get_background_session_factory()
        if session_factory:
            try:
                from ..db.repository import SettingsRepository

                async with session_factory() as session, session.begin():
                    existing = await SettingsRepository(session).get()
                    merged = {**existing, "global_paused": False}
                    await SettingsRepository(session).save(merged)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "failed to persist global_paused setting on resume",
                    extra=log_extra(error=str(exc)),
                )

        notify_new_task()

        if app_state.telegram is not None:
            try:
                await app_state.telegram.send_message("✅ 302 临时挑战解除，自动恢复下载")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "failed to send challenge resume telegram alert",
                    extra=log_extra(error=type(exc).__name__),
                )


async def challenge_probe_loop() -> None:
    """Periodically probe ExHentai if paused due to anti-abuse challenge."""
    while True:
        try:
            await asyncio.sleep(_CHALLENGE_PROBE_INTERVAL)
            settings = app_state.settings or get_settings()
            if not getattr(settings, "global_paused", False) or not app_state.extra.get(
                "auto_resume_challenge"
            ):
                continue

            client = app_state.eh_client
            if client is None and app_state.downloader is not None:
                client = getattr(app_state.downloader, "client", None)
            if client is None:
                continue

            sample_path = app_state.extra.get("challenge_sample_path", "/")
            cleared = await client.probe_challenge(sample_path)
            if cleared:
                logger.info("ExHentai anti-abuse challenge has cleared; resuming downloads")
                await _resume_challenge_pause()
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("challenge probe failed", extra=log_extra(error=type(exc).__name__))


async def _run_download_inner(
    task: DownloadTask,
    *,
    follow_hops: int = 0,
    replaced_from_gid: int | None = None,
) -> None:
    session_cm = _get_background_session_factory()
    if session_cm is None:
        return
    downloader = app_state.downloader
    if downloader is None:
        return
    notify_fn = record_download_notification
    maybe_scan_fn = maybe_scan_after_download

    row = None
    exec_task: DownloadTask | None = None
    try:
        if is_download_cancelled(task.id):
            raise DownloadCancelledError("download was cancelled")

        async with session_cm() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row is None or row.status == "cancelled" or is_download_cancelled(task.id):
                if row is not None and row.status != "cancelled":
                    row.status = "cancelled"
                    row.finished_at = datetime.now(UTC)
                clear_download_cancelled(task.id)
                return
            row.status = "downloading"
            row.started_at = datetime.now(UTC)

        exec_task = DownloadTask(
            task.gid,
            task.token,
            task.title,
            task.id,
            1,
            task.mode,
            task.category,
            max_pages=task.max_pages,
            quality=task.quality,
            archive_fallback=bool(getattr(task, "archive_fallback", False)),
        )

        progress_state = {"last_persisted": 0, "last_flush": 0.0}

        async def _on_progress(current: int, total: int) -> None:
            if is_download_cancelled(task.id):
                raise DownloadCancelledError("download was cancelled")
            now = _time.monotonic()
            if (
                current >= total
                or progress_state["last_persisted"] == 0
                or current - progress_state["last_persisted"] >= _PROGRESS_FLUSH_STEP
                or now - progress_state["last_flush"] >= _PROGRESS_FLUSH_INTERVAL
            ):
                if task.id is not None:
                    is_fb = bool(getattr(exec_task, "archive_fallback", False))
                    await download_progress(
                        task.id,
                        current,
                        total,
                        archive_fallback=True if is_fb else None,
                        gid=getattr(task, "gid", None),
                    )
                progress_state["last_persisted"] = current
                progress_state["last_flush"] = now

        if is_download_cancelled(task.id):
            raise DownloadCancelledError("download was cancelled")

        result = await downloader.execute(
            exec_task,
            progress=_on_progress,
        )
        if is_download_cancelled(task.id):
            if result and hasattr(result, "path") and Path(result.path).exists():
                import shutil

                p = Path(result.path)
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
            raise DownloadCancelledError("download was cancelled")
        completed = False
        now = datetime.now(UTC)
        update_values: dict[str, Any] = {
            "status": "success",
            "target_path": str(result.path),
            "category": result.category,
            "error_message": None,
            "retry_count": 0,
            "retry_at": None,
            "finished_at": now,
        }
        if getattr(exec_task, "archive_fallback", False):
            update_values["archive_fallback"] = True
        if result.title:
            update_values["title"] = result.title
        if getattr(result, "title_jpn", None):
            update_values["title_jpn"] = result.title_jpn
        if getattr(result, "pages", None):
            update_values["current_page"] = func.coalesce(
                DownloadTaskModel.total_pages, result.pages
            )
            update_values["total_pages"] = func.coalesce(
                DownloadTaskModel.total_pages, result.pages
            )

        async with session_cm() as session, session.begin():
            if hasattr(session, "execute"):
                stmt = (
                    update(DownloadTaskModel)
                    .where(
                        DownloadTaskModel.id == task.id,
                        DownloadTaskModel.status == "downloading",
                    )
                    .values(**update_values)
                )
                update_result = await session.execute(stmt)
                is_cancelled = bool(update_result.rowcount == 0)
            else:
                row = await session.get(DownloadTaskModel, task.id)
                if (
                    row is None
                    or row.status != "downloading"
                    or is_download_cancelled(task.id)
                ):
                    is_cancelled = True
                else:
                    is_cancelled = False
                    row.status = "success"
                    row.target_path = update_values.get("target_path")
                    row.category = update_values.get("category")
                    row.error_message = None
                    row.retry_count = 0
                    row.retry_at = None
                    row.finished_at = update_values.get("finished_at")
                    if "archive_fallback" in update_values:
                        row.archive_fallback = update_values["archive_fallback"]
                    if "title" in update_values:
                        row.title = update_values["title"]
                    if "title_jpn" in update_values:
                        row.title_jpn = update_values["title_jpn"]
                    if getattr(result, "pages", None):
                        row.current_page = getattr(row, "total_pages", None) or result.pages
                        row.total_pages = getattr(row, "total_pages", None) or result.pages

            if is_cancelled:
                if result and hasattr(result, "path") and Path(result.path).exists():
                    import shutil

                    p = Path(result.path)
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)
                raise DownloadCancelledError("download was cancelled")

            await DownloadRepository(session).record_attempt(
                task.id or 0, 1, "success"
            )
            completed = True

        clear_download_cancelled(task.id)
        if completed:
            old_gid: int | None = replaced_from_gid
            if old_gid is None and session_cm is not None:
                try:
                    async with session_cm() as session:
                        if hasattr(session, "scalars"):
                            update_row = (
                                await session.scalars(
                                    select(GalleryUpdate).where(
                                        GalleryUpdate.new_gid == task.gid
                                    )
                                )
                            ).first()
                            if update_row is not None:
                                old_gid = update_row.old_gid
                            else:
                                prev = (
                                    await session.scalars(
                                        select(Gallery).where(
                                            Gallery.gid == task.gid
                                        )
                                    )
                                ).first()
                                if prev is not None:
                                    old_gid = task.gid
                        elif hasattr(session, "scalar"):
                            update_row = await session.scalar(
                                select(GalleryUpdate).where(
                                    GalleryUpdate.new_gid == task.gid
                                )
                            )
                            if update_row is not None:
                                old_gid = update_row.old_gid
                            else:
                                prev = await session.scalar(
                                    select(Gallery).where(
                                        Gallery.gid == task.gid
                                    )
                                )
                                if prev is not None:
                                    old_gid = task.gid
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "failed to check update status for download notification",
                        extra=log_extra(gid=task.gid, error=type(exc).__name__),
                    )

            title = result.title or str(task.gid)
            if old_gid is not None:
                await notify_fn("updated", title, f"{old_gid}:{task.gid}")
            else:
                await notify_fn("ok", title, str(result.pages))
            maybe_scan_fn(result)
    except GalleryReplacedError as exc:
        from .download_prepare import MAX_FOLLOW_HOPS

        if follow_hops >= MAX_FOLLOW_HOPS:
            logger.warning(
                "download replacement hop limit",
                extra=log_extra(gid=task.gid, new_gid=exc.new_gid),
            )
            try:
                async with session_cm() as session, session.begin():
                    row = await session.get(DownloadTaskModel, task.id)
                    if row is not None and row.status != "cancelled":
                        row.status = "failed"
                        row.error_message = HOPS_DETAIL
                        row.retry_count = row.max_retries
                        row.finished_at = datetime.now(UTC)
            except SQLAlchemyError:
                pass
            return
        rewritten = await _apply_replacement(task, exc)
        if rewritten is None:
            return
        await _run_download_inner(
            rewritten,
            follow_hops=follow_hops + 1,
            replaced_from_gid=replaced_from_gid or exc.old_gid,
        )
    except DownloadCancelledError:
        try:
            async with session_cm() as session, session.begin():
                row = await session.get(DownloadTaskModel, task.id)
                if row is not None and row.status != "cancelled":
                    row.status = "cancelled"
                    row.finished_at = datetime.now(UTC)
        except SQLAlchemyError:
            pass
        settings = app_state.settings or get_settings()
        try:
            temp = Path(settings.download_root) / f".gv-{task.gid}"
            if temp.exists():
                import shutil

                from .storage_usage import safe_stat_size, storage_tracker

                sz = safe_stat_size(temp)
                shutil.rmtree(temp, ignore_errors=True)
                if sz > 0:
                    storage_tracker.record_download_delta(-sz)
        except OSError:
            pass
        clear_download_cancelled(task.id)
        logger.info("download cancelled", extra=log_extra(gid=task.gid))
    except EhChallengeError as exc:
        http_meta = _extract_http_meta(exc)
        challenge_extra: dict[str, Any] = {
            "task_id": task.id,
            "gid": task.gid,
            "error": str(exc),
        }
        challenge_extra.update(http_meta)
        logger.warning(
            "download challenge encountered; auto-pausing downloads",
            extra=log_extra(**challenge_extra),
        )
        now = datetime.now(UTC)
        try:
            async with session_cm() as session, session.begin():
                row = await session.get(DownloadTaskModel, task.id)
                if row and row.status != "cancelled":
                    row.status = "pending"
                    row.retry_at = now + timedelta(seconds=retry_backoff(row.retry_count or 1))
                    row.error_message = "自动暂停：检测到 ExHentai 302 临时挑战"
                    row.updated_at = now
                    await DownloadRepository(session).record_attempt(
                        task.id or 0, row.retry_count, "challenged", "EhChallengeError"
                    )
        except SQLAlchemyError as db_exc:
            logger.exception(
                "download status persistence failed on challenge",
                extra=log_extra(
                    task_id=task.id,
                    gid=task.gid,
                    error=str(db_exc) or type(db_exc).__name__,
                ),
            )
        sample_path = f"/g/{task.gid}/{task.token}/" if task.token else "/"
        await _trigger_challenge_pause(
            sample_path,
            task_id=task.id,
            gid=task.gid,
            response_meta=http_meta,
        )
    except Exception as exc:
        http_meta = _extract_http_meta(exc)
        fail_extra: dict[str, Any] = {
            "task_id": task.id,
            "gid": task.gid,
            "error": type(exc).__name__,
            "message": str(exc),
        }
        fail_extra.update(http_meta)
        logger.exception(
            "download task failed",
            extra=log_extra(**fail_extra),
        )
        try:
            gone = False
            async with session_cm() as session, session.begin():
                row = await session.get(DownloadTaskModel, task.id)
                if row and row.status != "cancelled":
                    now = datetime.now(UTC)
                    auth_failure = "authenticat" in str(exc)
                    gone = isinstance(exc, GalleryGoneError) or "does not exist on ExHentai" in str(
                        exc
                    )
                    not_retryable = (
                        isinstance(exc, (ArchiveNotRetryableError, GalleryGoneError))
                        or gone
                    )
                    row.retry_count += 1
                    if auth_failure or not_retryable or row.retry_count >= row.max_retries:
                        row.status = "failed"
                        row.retry_at = None
                        row.finished_at = now
                        row.retry_count = max(row.retry_count, row.max_retries)
                    else:
                        row.status = "pending"
                        # Always apply exponential backoff for transient errors so the
                        # 60s sweep does not instantly re-claim a just-failed task.
                        # The old `challenge ? backoff : now` caused non-challenge
                        # EhClientError to be retried in <1s, burning the retry budget.
                        row.retry_at = now + timedelta(seconds=retry_backoff(row.retry_count))
                    if exec_task is not None and getattr(exec_task, "archive_fallback", False):
                        row.archive_fallback = True
                    row.error_message = GONE_DETAIL if gone else f"{type(exc).__name__}: {exc}"
                    row.updated_at = now
                    await DownloadRepository(session).record_attempt(
                        task.id or 0, row.retry_count, "failed", type(exc).__name__
                    )
            if row is not None and row.status == "failed":
                await notify_fn(
                    "fail",
                    task.title or str(task.gid),
                    GONE_DETAIL if gone else type(exc).__name__,
                )
        except SQLAlchemyError as db_exc:
            logger.error(
                "download status persistence failed",
                extra=log_extra(error=str(db_exc) or type(db_exc).__name__),
            )


def _effective_download_concurrency(concurrency: int | None = None) -> int:
    if concurrency is None:
        settings = app_state.settings or get_settings()
        concurrency = getattr(settings, "download_concurrency", 2)
    c = max(1, int(concurrency))
    try:
        engine = app_state.engine
        if engine is not None and getattr(engine.dialect, "name", "") == "sqlite":
            c = 1
    except Exception:  # noqa: BLE001, S110
        pass
    return c


async def _download_worker() -> None:
    global _worker_tasks
    while True:
        try:
            # Cooperative drain: if target concurrency decreased, exit after completing current gallery
            current_task = asyncio.current_task()
            _worker_tasks = [t for t in _worker_tasks if not t.done()]
            if current_task is not None and current_task not in _worker_tasks:
                return
            if len(_worker_tasks) > _target_download_concurrency:
                if current_task in _worker_tasks:
                    _worker_tasks.remove(current_task)
                logger.info(
                    "Download worker exiting cooperatively for concurrency drain",
                    extra=log_extra(current=len(_worker_tasks), target=_target_download_concurrency),
                )
                return

            # Global pause: stop claiming new galleries (current page finishes)
            try:
                _settings = app_state.settings or get_settings()
                if getattr(_settings, "global_paused", False):
                    await asyncio.sleep(5)
                    continue
            except Exception:  # noqa: BLE001, S110
                pass
            row = None
            session_factory = _get_background_session_factory()
            if not session_factory:
                if _task_event is not None:
                    try:
                        await asyncio.wait_for(_task_event.wait(), timeout=1.0)
                    except TimeoutError:
                        pass
                    _task_event.clear()
                else:
                    await asyncio.sleep(0.5)
                continue
            async with session_factory() as session, session.begin():
                row = await DownloadRepository(session).claim_pending()
                if row is not None:
                    task = DownloadTask(
                        row.gid,
                        row.token,
                        row.title or str(row.gid),
                        row.id,
                        row.max_retries,
                        row.mode,
                        row.category or "other",
                        max_pages=row.max_pages,
                        quality=row.quality,
                    )
            if row is not None:
                if _task_event is not None:
                    _task_event.clear()
                try:
                    await run_download(task)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception(
                        "run_download unhandled exception",
                        extra=log_extra(task_id=task.id, gid=task.gid, error=str(exc) or type(exc).__name__),
                    )
                    if session_factory and task.id:
                        try:
                            async with session_factory() as session, session.begin():
                                r = await session.get(DownloadTaskModel, task.id)
                                if r and r.status not in ("cancelled", "failed"):
                                    now = datetime.now(UTC)
                                    r.retry_count += 1
                                    if r.retry_count >= r.max_retries:
                                        r.status = "failed"
                                        r.retry_at = None
                                        r.finished_at = now
                                    else:
                                        r.status = "pending"
                                        r.retry_at = now + timedelta(seconds=retry_backoff(r.retry_count))
                                    r.error_message = f"UnhandledWorkerError: {exc}"
                                    r.updated_at = now
                        except Exception:  # noqa: BLE001, S110
                            pass
            else:
                if _task_event is not None:
                    try:
                        await asyncio.wait_for(_task_event.wait(), timeout=5.0)
                    except TimeoutError:
                        pass
                    _task_event.clear()
                else:
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "download worker iteration failed",
                extra=log_extra(error=str(exc) or type(exc).__name__),
            )
            await asyncio.sleep(2)


def adjust_download_concurrency(new_concurrency: int | None = None) -> None:
    global _worker_tasks, _task_event, _target_download_concurrency
    if _task_event is None:
        _task_event = asyncio.Event()
    target = _effective_download_concurrency(new_concurrency)
    _target_download_concurrency = target
    _worker_tasks = [t for t in _worker_tasks if not t.done()]
    current = len(_worker_tasks)
    if target > current:
        for _ in range(target - current):
            _worker_tasks.append(asyncio.create_task(_download_worker()))
        logger.info(
            "Adjusted download concurrency",
            extra=log_extra(previous=current, target=target, current=len(_worker_tasks)),
        )
    elif target < current:
        logger.info(
            "Set target download concurrency for cooperative drain",
            extra=log_extra(previous=current, target=target, current=len(_worker_tasks)),
        )
        notify_new_task()


async def download_worker_loop() -> None:
    """Recover and claim persisted jobs continuously."""
    session_factory = _get_background_session_factory()
    if not session_factory:
        return
    try:
        async with session_factory() as session, session.begin():
            await DownloadRepository(session).recover_orphans()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "download recovery failed",
            extra=log_extra(error=str(exc) or type(exc).__name__),
        )

    global _task_event
    if _task_event is None:
        _task_event = asyncio.Event()

    adjust_download_concurrency()

    probe_task = asyncio.create_task(challenge_probe_loop())

    try:
        while True:
            await asyncio.sleep(10)
            global _worker_tasks, _target_download_concurrency
            _worker_tasks = [t for t in _worker_tasks if not t.done()]
            settings = app_state.settings or get_settings()
            target = _effective_download_concurrency(settings.download_concurrency)
            _target_download_concurrency = target
            if len(_worker_tasks) < target:
                for _ in range(target - len(_worker_tasks)):
                    _worker_tasks.append(asyncio.create_task(_download_worker()))
    except asyncio.CancelledError:
        probe_task.cancel()
        for t in _worker_tasks:
            t.cancel()
        tasks_to_wait = [probe_task, *_worker_tasks]
        if tasks_to_wait:
            await asyncio.gather(*tasks_to_wait, return_exceptions=True)
        _worker_tasks.clear()
        raise


async def download_retry_sweep_loop() -> None:
    """Auto-requeue failed downloads that still have retry budget left."""
    while True:
        await asyncio.sleep(_DOWNLOAD_RETRY_SWEEP_INTERVAL)
        session_factory = _get_background_session_factory()
        if not session_factory:
            continue
        from ..app.dependencies import get_task_manager

        tm = get_task_manager()
        try:
            async with (
                tm.track_task("download-retry-sweep", record_if_empty=False) as tracker,
                session_factory() as session,
                session.begin(),
            ):
                requeued = await DownloadRepository(session).sweep_auto_retry()
                tracker.update(done=requeued, total=requeued)
                if requeued:
                    notify_new_task()
                    logger.info("requeued failed downloads", extra=log_extra(count=requeued))
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "download retry sweep failed", extra=log_extra(error=type(exc).__name__)
            )
