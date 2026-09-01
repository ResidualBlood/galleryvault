"""Background worker loops and post-processing for downloads."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time as _time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..app.state import app_state
from ..config import get_settings
from ..db.models import DownloadTask as DownloadTaskModel
from ..db.models import Gallery
from ..db.repository import DownloadRepository
from ..logging import log_extra
from ..scanners import registry
from ..scanners.base import GalleryMeta, PageInfo
from ..scanners.ehviewer import IMAGE_EXTENSIONS, natural_key
from .deletion import prune_merged_stale_pages, remove_superseded_copy
from .downloader import (
    ArchiveNotRetryableError,
    DownloadCancelledError,
    DownloadTask,
)
from .eh_client import EhClientError  # noqa: F401  # kept for backoff classification docs
from .ingest import GalleryIngestService

logger = logging.getLogger(__name__)

_RETRY_BACKOFFS = (
    30, 120, 480, 1800, 3600, 7200, 10800, 14400, 18000, 21600,
)
_PROGRESS_FLUSH_STEP = 20
_PROGRESS_FLUSH_INTERVAL = 5.0
_DOWNLOAD_RETRY_SWEEP_INTERVAL = 60.0
_TELEGRAM_FLUSH_INTERVAL = 60.0


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
    from ..app import main
    try:
        path = Path(result.path)
        reg = getattr(main, "registry", registry)
        scanner = reg.for_path(path)
        if scanner is None:
            logger.warning("download ingest: no scanner for path", extra=log_extra(path=str(path)))
            return

        if getattr(result, "quality", None) == "original":
            await asyncio.to_thread(
                prune_merged_stale_pages, path, getattr(result, "new_files", ())
            )

        files = sorted(
            (
                item
                for item in path.iterdir()
                if item.is_file()
                and not item.name.startswith(".")
                and item.suffix.casefold() in IMAGE_EXTENSIONS
            ),
            key=lambda item: natural_key(item.name),
        )
        pages = [
            PageInfo(
                i,
                item.name,
                item.suffix.casefold().lstrip("."),
                item.stat().st_size,
                item.stat().st_mtime_ns,
            )
            for i, item in enumerate(files)
        ]
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

        ingest_cls = getattr(main, "GalleryIngestService", GalleryIngestService)
        remove_fn = getattr(main, "_remove_superseded_copy", remove_superseded_copy)
        session_cm = getattr(main, "_settings_session", None) or (app_state.session_factory if app_state else None)
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
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "download ingest failed",
            extra=log_extra(gid=getattr(result, "gid", None), error=type(exc).__name__),
        )


def maybe_scan_after_download(result: Any) -> None:
    """Ingest just the single downloaded gallery unless full scan is running."""
    tm = app_state.task_manager
    if tm and tm.scan_state.get("running"):
        return
    from ..app.dependencies import spawn_task
    spawn_task(ingest_downloaded_gallery(result), "download ingest")


async def download_progress(task_id: int | None, current_page: int, total_pages: int) -> None:
    if task_id is None or not app_state.session_factory:
        return
    try:
        async with app_state.session_factory() as session, session.begin():
            await DownloadRepository(session).progress(task_id, current_page, total_pages)
    except SQLAlchemyError as exc:
        logger.warning(
            "download progress persistence failed", extra=log_extra(error=type(exc).__name__)
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
    if not app_state.session_factory:
        return
    try:
        async with app_state.session_factory() as session:
            active = await DownloadRepository(session).count_active()
        if active == 0:
            await notifier.flush_summary()
    except SQLAlchemyError as exc:
        logger.warning(
            "telegram summary flush check failed", extra=log_extra(error=type(exc).__name__)
        )


async def telegram_flush_loop() -> None:
    while True:
        await asyncio.sleep(_TELEGRAM_FLUSH_INTERVAL)
        notifier = app_state.telegram
        if notifier is not None:
            try:
                if notifier.events_stale(_TELEGRAM_FLUSH_INTERVAL):
                    await notifier.flush_summary()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "telegram summary flush failed", extra=log_extra(error=type(exc).__name__)
                )


def is_download_cancelled(task_id: int | None) -> bool:
    if task_id is None:
        return False
    tm = app_state.task_manager
    if tm and tm.is_cancelled(task_id):
        return True
    from ..app import main
    cancelled_set = getattr(main, "_download_cancelled", None)
    if cancelled_set is not None and (isinstance(cancelled_set, set) or hasattr(cancelled_set, "__contains__")):
        return task_id in cancelled_set
    return False


def clear_download_cancelled(task_id: int | None) -> None:
    if task_id is None:
        return
    tm = app_state.task_manager
    if tm:
        tm.clear_cancelled(task_id)
    from ..app import main
    cancelled_set = getattr(main, "_download_cancelled", None)
    if cancelled_set is not None and (isinstance(cancelled_set, set) or hasattr(cancelled_set, "discard")):
        with contextlib.suppress(Exception):
            cancelled_set.discard(task_id)


def mark_download_cancelled(task_id: int | None) -> None:
    if task_id is None:
        return
    tm = app_state.task_manager
    if tm:
        tm.request_cancel(task_id)
    from ..app import main
    cancelled_set = getattr(main, "_download_cancelled", None)
    if cancelled_set is not None and (isinstance(cancelled_set, set) or hasattr(cancelled_set, "add")):
        with contextlib.suppress(Exception):
            cancelled_set.add(task_id)


async def run_download(task: DownloadTask) -> None:
    if task.id is None:
        logger.warning("download task missing id; skipping", extra=log_extra(gid=task.gid))
        return
    from ..app import main
    session_cm = getattr(main, "_settings_session", None) or (app_state.session_factory if app_state else None)
    if session_cm is None:
        return
    st = getattr(getattr(main, "app", None), "state", None)
    downloader = getattr(st, "downloader", None) or app_state.downloader
    if downloader is None:
        return
    notify_fn = getattr(main, "_record_download_notification", record_download_notification)
    maybe_scan_fn = getattr(main, "_maybe_scan_after_download", maybe_scan_after_download)

    row = None
    try:
        async with session_cm() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row is None or row.status == "cancelled":
                return
            row.status = "downloading"
            row.started_at = datetime.now(UTC)

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
                    await download_progress(task.id, current, total)
                progress_state["last_persisted"] = current
                progress_state["last_flush"] = now

        result = await downloader.execute(
            DownloadTask(
                task.gid,
                task.token,
                task.title,
                task.id,
                1,
                task.mode,
                task.category,
                max_pages=task.max_pages,
                quality=task.quality,
            ),
            progress=_on_progress,
        )
        completed = False
        async with session_cm() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row is not None:
                if row.status == "cancelled" or is_download_cancelled(task.id):
                    raise DownloadCancelledError("download was cancelled")
                row.status, row.target_path, row.category = (
                    "success",
                    str(result.path),
                    result.category,
                )
                if getattr(row, "total_pages", None):
                    row.current_page = row.total_pages
                elif getattr(result, "pages", None) and hasattr(row, "current_page"):
                    row.current_page = result.pages
                    if hasattr(row, "total_pages"):
                        row.total_pages = result.pages
                row.error_message = None
                row.retry_count = 0
                row.retry_at = None
                row.finished_at = datetime.now(UTC)
                await DownloadRepository(session).record_attempt(
                    task.id or 0, row.retry_count + 1, "success"
                )
                completed = True

        clear_download_cancelled(task.id)
        if completed:
            await notify_fn("ok", result.title or str(task.gid), str(result.pages))
            maybe_scan_fn(result)
    except DownloadCancelledError:
        settings = getattr(main, "_settings", lambda: app_state.settings or get_settings())()
        try:
            temp = Path(settings.download_root) / f".gv-{task.gid}"
            if temp.exists():
                import shutil
                shutil.rmtree(temp, ignore_errors=True)
        except OSError:
            pass
        clear_download_cancelled(task.id)
        logger.info("download cancelled", extra=log_extra(gid=task.gid))
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "download task failed", extra=log_extra(gid=task.gid, error=type(exc).__name__)
        )
        try:
            async with session_cm() as session, session.begin():
                row = await session.get(DownloadTaskModel, task.id)
                if row and row.status != "cancelled":
                    now = datetime.now(UTC)
                    auth_failure = "authenticat" in str(exc)
                    not_retryable = isinstance(exc, ArchiveNotRetryableError)
                    row.retry_count += 1
                    if auth_failure or not_retryable or row.retry_count >= row.max_retries:
                        row.status = "failed"
                        row.retry_at = None
                        row.finished_at = now
                    else:
                        row.status = "pending"
                        # Always apply exponential backoff for transient errors so the
                        # 60s sweep does not instantly re-claim a just-failed task.
                        # The old `challenge ? backoff : now` caused non-challenge
                        # EhClientError to be retried in <1s, burning the retry budget.
                        row.retry_at = now + timedelta(seconds=retry_backoff(row.retry_count))
                    row.error_message = f"{type(exc).__name__}: {exc}"
                    row.updated_at = now
                    await DownloadRepository(session).record_attempt(
                        task.id or 0, row.retry_count, "failed", type(exc).__name__
                    )
            if row is not None and row.status == "failed":
                await notify_fn(
                    "fail", task.title or str(task.gid), type(exc).__name__
                )
        except SQLAlchemyError as db_exc:
            logger.error(
                "download status persistence failed", extra=log_extra(error=type(db_exc).__name__)
            )


async def download_worker_loop() -> None:
    """Recover and claim persisted jobs continuously."""
    if not app_state.session_factory:
        return
    try:
        async with app_state.session_factory() as session, session.begin():
            await DownloadRepository(session).recover_orphans()
    except Exception as exc:  # noqa: BLE001
        logger.warning("download recovery failed", extra=log_extra(error=type(exc).__name__))

    settings = app_state.settings or get_settings()
    concurrency = max(1, settings.download_concurrency)
    # SQLite does not support FOR UPDATE SKIP LOCKED — multiple workers would
    # repeatedly claim the same row. Force single worker in that case.
    try:
        engine = app_state.engine
        if engine is not None and getattr(engine.dialect, "name", "") == "sqlite":
            concurrency = 1
    except Exception:  # noqa: BLE001, S110
        pass

    async def _worker() -> None:
        while True:
            try:
                row = None
                async with app_state.session_factory() as session, session.begin():
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
                    await run_download(task)
                else:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "download worker iteration failed", extra=log_extra(error=type(exc).__name__)
                )
                await asyncio.sleep(2)

    workers = [asyncio.create_task(_worker()) for _ in range(concurrency)]
    try:
        await asyncio.gather(*workers)
    finally:
        pass


async def download_retry_sweep_loop() -> None:
    """Auto-requeue failed downloads that still have retry budget left."""
    while True:
        await asyncio.sleep(_DOWNLOAD_RETRY_SWEEP_INTERVAL)
        if not app_state.session_factory:
            continue
        try:
            async with app_state.session_factory() as session, session.begin():
                requeued = await DownloadRepository(session).sweep_auto_retry()
                if requeued:
                    logger.info("requeued failed downloads", extra=log_extra(count=requeued))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "download retry sweep failed", extra=log_extra(error=type(exc).__name__)
            )
