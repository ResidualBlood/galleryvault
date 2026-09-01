"""Background worker loop for generating cached gallery thumbnails."""

from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..app.state import app_state
from ..config import get_settings
from ..db.models import Gallery, GalleryPage
from ..db.repository import BackgroundJobsRepository
from ..logging import bind_log_context, log_extra
from ..scanners import registry
from ..scanners.base import GalleryMeta, PageInfo
from .tag_sync_worker import claim_jobs, complete_job, jobs_count, requeue_job
from .thumbnails import ThumbnailError, ThumbnailService

logger = logging.getLogger(__name__)

JOB_THUMB = BackgroundJobsRepository.JOB_THUMB
_THUMB_POLL_INTERVAL = 1.0
_THUMB_IDLE_SECONDS = 5.0


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


async def thumbnail_gallery(gallery_id: int) -> tuple[int, int]:
    if not app_state.session_factory:
        return 0, 0
    generated = 0
    failed_pages = 0
    tm = app_state.task_manager
    thumb_state = tm.thumb_state if tm else {}

    async with app_state.session_factory() as session:
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
        except (ThumbnailError, OSError, EOFError) as exc:
            failed_pages += 1
            thumb_state["last_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
    return generated, failed_pages


async def seed_thumbnails() -> None:
    if not app_state.session_factory:
        return
    with bind_log_context(worker="thumbnails"):
        async with app_state.session_factory() as session:
            rows = await session.execute(
                select(Gallery.id, Gallery.page_count).where(
                    Gallery.page_count.is_not(None), Gallery.expunged.is_(False)
                )
            )
            pairs = [(int(row[0]), int(row[1])) for row in rows if row[1]]
        service = _thumb_service()
        missing: list[int] = []
        missing_total = 0
        for gallery_id, _page_count in pairs:
            if service.cached(gallery_id, 0) is not None:
                continue
            missing_total += 1
            missing.append(gallery_id)
        added = 0
        for start in range(0, len(missing), 500):
            async with app_state.session_factory() as session, session.begin():
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
    if not app_state.session_factory:
        return
    concurrency = 4
    tm = app_state.task_manager
    thumb_state = tm.thumb_state if tm else {}
    thumb_state["running"] = True
    last_activity = [_time.monotonic()]

    try:
        async with app_state.session_factory() as session, session.begin():
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
                        await requeue_job(JOB_THUMB, gallery_id)
                    else:
                        await complete_job(JOB_THUMB, gallery_id)
                else:
                    thumb_state["succeeded"] = thumb_state.get("succeeded", 0) + 1
                    await complete_job(JOB_THUMB, gallery_id)
            except Exception as exc:  # noqa: BLE001
                thumb_state["failed"] = thumb_state.get("failed", 0) + 1
                thumb_state["last_error"] = f"{type(exc).__name__}: {exc}"
                if attempts < 3:
                    await requeue_job(JOB_THUMB, gallery_id)
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
