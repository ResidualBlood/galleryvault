"""Background worker loop for generating cached gallery thumbnails."""

from __future__ import annotations

import asyncio
import logging
import shutil
import time as _time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..app.state import app_state
from ..config import get_settings
from ..db.models import Gallery, GalleryPage
from ..db.repository import BackgroundJobsRepository
from ..logging import bind_log_context, log_extra
from ..scanners import registry
from ..scanners.base import GalleryMeta, PageInfo
from .storage_usage import safe_stat_size, storage_tracker
from .tag_sync_worker import claim_jobs, complete_job, jobs_count, requeue_job
from .thumbnails import ThumbnailError, ThumbnailService

logger = logging.getLogger(__name__)

JOB_THUMB = BackgroundJobsRepository.JOB_THUMB
_THUMB_POLL_INTERVAL = 1.0
_THUMB_IDLE_SECONDS = 5.0


def _get_background_session_factory() -> Any:
    return getattr(app_state, "background_session_factory", None) or app_state.session_factory


def _thumb_service() -> ThumbnailService:
    if app_state.thumbnail_service is not None:
        return app_state.thumbnail_service
    settings = app_state.settings or get_settings()
    service = ThumbnailService(settings.thumbnail_cache_dir)
    app_state.thumbnail_service = service
    return service


def _meta(gallery: Gallery, pages: list[GalleryPage]) -> GalleryMeta:
    return GalleryMeta(
        title=gallery.title or "",
        path=Path(gallery.storage_path or ""),
        storage_type=gallery.storage_type or "ehviewer_dir",
        pages=[
            PageInfo(
                p.page_index,
                p.member_name or f"{p.page_index:04d}",
                p.media_type or "jpg",
            )
            for p in pages
        ],
        gid=gallery.gid,
        token=gallery.token,
        title_jpn=gallery.title_jpn,
        category=gallery.category,
        uploader=gallery.uploader,
        file_count=gallery.page_count or 0,
        file_size=gallery.file_size or gallery.storage_size or 0,
        rating=gallery.rating,
        posted_at=gallery.posted_at,
        tags=[],
        storage_signature=gallery.storage_signature or "",
        storage_mtime_ns=gallery.storage_mtime_ns,
        storage_size=gallery.storage_size or 0,
    )


def _touch_placeholder(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


async def thumbnail_gallery(gallery_id: int) -> tuple[int, int]:
    session_factory = _get_background_session_factory()
    if not session_factory:
        return 0, 0
    generated = 0
    failed_pages = 0
    tm = app_state.task_manager
    thumb_state = tm.thumb_state if tm else {}

    async with session_factory() as session:
        row = await session.get(Gallery, gallery_id)
        if row is None or not row.page_count:
            return 0, 0
        pages = list(
            await session.scalars(
                select(GalleryPage)
                .where(GalleryPage.gallery_id == gallery_id)
                .order_by(GalleryPage.page_index)
            )
        )
    service = _thumb_service()
    if not row.storage_path:
        return 0, 0
    scanner = registry.for_path(Path(row.storage_path))
    if scanner is None:
        return 0, 0
    meta = _meta(row, pages)
    for page in pages:
        if service.cached(gallery_id, page.page_index) is not None:
            continue
        stream = None
        try:
            stream = await run_in_threadpool(
                scanner.open_page,
                meta,
                PageInfo(page.page_index, page.member_name or "", page.media_type or "jpg"),
            )
            data = await run_in_threadpool(stream.read)
            await run_in_threadpool(service.get_or_create, gallery_id, page.page_index, data)
            generated += 1
        except (ThumbnailError, OSError, EOFError, KeyError, ValueError) as exc:
            failed_pages += 1
            thumb_state["last_error"] = f"{type(exc).__name__}: {exc}"
            try:
                await run_in_threadpool(
                    _touch_placeholder, service.cache_path(gallery_id, page.page_index)
                )
            except OSError:
                pass
        finally:
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        await asyncio.sleep(0.01)
    return generated, failed_pages


async def seed_thumbnails() -> None:
    session_factory = _get_background_session_factory()
    if not session_factory:
        return
    with bind_log_context(worker="thumbnails"):
        async with session_factory() as session:
            rows = await session.execute(
                select(Gallery.id, Gallery.page_count).where(
                    Gallery.page_count.is_not(None), Gallery.expunged.is_(False)
                )
            )
            pairs = [(int(row[0]), int(row[1])) for row in rows if row[1]]
        service = _thumb_service()
        missing: list[int] = []

        def _check_missing(chunk: list[tuple[int, int]]) -> list[int]:
            return [gid for gid, count in chunk if service.has_missing_pages(gid, count)]

        for start in range(0, len(pairs), 500):
            chunk = pairs[start : start + 500]
            missing.extend(await asyncio.to_thread(_check_missing, chunk))
            await asyncio.sleep(0.01)

        missing_total = len(missing)
        added = 0
        for start in range(0, len(missing), 500):
            async with session_factory() as session, session.begin():
                added += await BackgroundJobsRepository(session).enqueue_many(
                    JOB_THUMB, missing[start : start + 500]
                )
        tm = app_state.task_manager
        thumb_state = tm.thumb_state if tm else {}
        thumb_state["total"] = missing_total
        thumb_state["queued"] = await jobs_count(JOB_THUMB)
        if added:
            thumb_state["running"] = True
            thumb_state["completed_at"] = None
        logger.info("thumbnail seeding complete", extra=log_extra(queued=added, pending=missing_total))


async def thumbnail_worker_loop() -> None:
    session_factory = _get_background_session_factory()
    if not session_factory:
        return
    settings = app_state.settings or get_settings()
    concurrency = settings.thumbnail_workers
    tm = app_state.task_manager
    thumb_state = tm.thumb_state if tm else {}
    thumb_state["running"] = True
    last_activity = [_time.monotonic()]

    try:
        async with session_factory() as session, session.begin():
            await BackgroundJobsRepository(session).mark_stale()
    except Exception as exc:  # noqa: BLE001
        logger.warning("thumbnail stale-recovery failed", extra=log_extra(error=type(exc).__name__))

    async def _worker() -> None:
        while True:
            if tm and tm.is_cancelled("thumbs"):
                break
            claimed = await claim_jobs(JOB_THUMB, 1)
            if not claimed:
                if (
                    _time.monotonic() - last_activity[0] >= _THUMB_IDLE_SECONDS
                    and thumb_state.get("running")
                ):
                    thumb_state["completed_at"] = datetime.now(UTC).isoformat()
                    thumb_state["queued"] = await jobs_count(JOB_THUMB)
                    thumb_state["running"] = False
                    if thumb_state.get("started_at") and not thumb_state.get("history_recorded"):
                        thumb_state["history_recorded"] = True
                        if tm:
                            tm.record_task(
                                "thumbs",
                                thumb_state.get("started_at"),
                                thumb_state["completed_at"],
                                "success",
                                reason=f"ok {thumb_state.get('succeeded', 0)} fail {thumb_state.get('failed', 0)}",
                                done=int(thumb_state.get("processed") or 0),
                                total=int(thumb_state.get("total") or 0),
                            )
                            from ..app.dependencies import spawn_task

                            spawn_task(tm.persist_history(), "persist task history")
                await asyncio.sleep(_THUMB_POLL_INTERVAL)
                continue

            last_activity[0] = _time.monotonic()
            if not thumb_state.get("running"):
                thumb_state["running"] = True
                thumb_state["started_at"] = datetime.now(UTC).isoformat()
                thumb_state["completed_at"] = None
                thumb_state["history_recorded"] = False

            gallery_id, attempts = claimed[0]
            thumb_state["queued"] = await jobs_count(JOB_THUMB)
            try:
                _generated, failed_pages = await thumbnail_gallery(gallery_id)
                if failed_pages:
                    thumb_state["failed"] = thumb_state.get("failed", 0) + 1
                    if attempts < 3:
                        delay = min(300, 10 * (2 ** max(0, attempts - 1)))
                        next_retry = datetime.now(UTC) + timedelta(seconds=delay)
                        await requeue_job(JOB_THUMB, gallery_id, next_attempt_at=next_retry)
                    else:
                        await complete_job(JOB_THUMB, gallery_id)
                else:
                    thumb_state["succeeded"] = thumb_state.get("succeeded", 0) + 1
                    await complete_job(JOB_THUMB, gallery_id)
            except Exception as exc:  # noqa: BLE001
                thumb_state["failed"] = thumb_state.get("failed", 0) + 1
                thumb_state["last_error"] = f"{type(exc).__name__}: {exc}"
                if attempts < 3:
                    delay = min(300, 10 * (2 ** max(0, attempts - 1)))
                    next_retry = datetime.now(UTC) + timedelta(seconds=delay)
                    await requeue_job(JOB_THUMB, gallery_id, next_attempt_at=next_retry)
                else:
                    await complete_job(JOB_THUMB, gallery_id)
            thumb_state["processed"] = (
                thumb_state.get("succeeded", 0) + thumb_state.get("failed", 0)
            )
            thumb_state["queued"] = await jobs_count(JOB_THUMB)

    workers = [asyncio.create_task(_worker()) for _ in range(concurrency)]
    try:
        await asyncio.gather(*workers)
    finally:
        pass


async def orphan_thumbnail_cleanup_loop() -> None:
    while True:
        try:
            await asyncio.sleep(86400)
            session_factory = _get_background_session_factory()
            if not session_factory:
                continue
            settings = app_state.settings or get_settings()
            cache_dir = Path(settings.thumbnail_cache_dir)
            if not cache_dir.exists():
                continue
            disk_ids: set[int] = {
                int(p.name) for p in cache_dir.iterdir() if p.is_dir() and p.name.isdigit()
            }
            if not disk_ids:
                continue
            from ..app.dependencies import get_task_manager

            tm = get_task_manager()
            async with tm.track_task("orphan-thumbnail-cleanup") as tracker:
                async with session_factory() as session:
                    rows = await session.scalars(select(Gallery.id))
                    db_ids = set(rows)
                orphan_ids = disk_ids - db_ids
                for gid in orphan_ids:
                    folder = cache_dir / str(gid)
                    if folder.exists() and folder.is_dir():
                        sz = safe_stat_size(folder)
                        shutil.rmtree(folder, ignore_errors=True)
                        if sz > 0:
                            storage_tracker.record_cache_delta(-sz)
                tracker.update(done=len(orphan_ids), total=len(disk_ids))
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("orphan thumbnail cleanup failed", extra=log_extra(error=type(exc).__name__))


async def thumbnail_periodic_seed_loop() -> None:
    while True:
        try:
            await asyncio.sleep(3600)
            settings = app_state.settings or get_settings()
            if settings.generate_thumbnails:
                from ..app.dependencies import get_task_manager

                tm = get_task_manager()
                if tm.thumb_state.get("running"):
                    continue
                async with tm.track_task("thumbnail-periodic-seed"):
                    await seed_thumbnails()
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("periodic thumbnail seeding failed", extra=log_extra(error=type(exc).__name__))

