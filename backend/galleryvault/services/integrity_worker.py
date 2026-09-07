"""Integrity magic scan worker (background scan for bad page headers)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from ..app.state import app_state
from ..config import get_settings
from ..db.repositories.galleries import GalleryRepository, _is_valid_page_header
from ..logging import bind_log_context, log_extra

logger = logging.getLogger(__name__)

MAGIC_SCAN_GALLERY_CONCURRENCY = 2
integrity_scan_lock = asyncio.Lock()


def gallery_has_bad_page_magic(storage_path: str, page_count: int) -> bool:
    """Check whether a gallery has missing, unreadable, or invalid magic page files."""
    if not storage_path:
        return False
    storage_dir = Path(storage_path)
    if not storage_dir.is_dir():
        return False

    for idx in range(page_count):
        try:
            matches = list(storage_dir.glob(f"{idx + 1:08d}.*"))
            if not matches:
                matches = list(storage_dir.glob(f"{idx + 1:04d}.*"))
        except OSError:
            return True

        page_found = False
        for candidate in matches:
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    with candidate.open("rb") as f:
                        head = f.read(20)
                    if _is_valid_page_header(head):
                        page_found = True
                        break
            except OSError:
                continue

        if not page_found:
            return True

    return False


async def run_integrity_magic_scan() -> None:
    """Background task scanning complete galleries for bad image magic bytes."""
    if not app_state.session_factory:
        return

    settings = app_state.settings or get_settings()
    from ..app.dependencies import get_task_manager

    tm = get_task_manager()
    if getattr(settings, "global_paused", False):
        tm.integrity_state["running"] = False
        return

    with bind_log_context(task="integrity_magic_scan"):
        async with integrity_scan_lock, tm.track_task("integrity") as tracker:
            tracker.update(corrupt_ids=[], scanned=0, last_error=None)

            semaphore = asyncio.Semaphore(MAGIC_SCAN_GALLERY_CONCURRENCY)
            after_id = 0

            async def _scan_one(gallery_id: int, storage_path: str, page_count: int) -> tuple[int, bool]:
                async with semaphore:
                    has_issue = await run_in_threadpool(
                        gallery_has_bad_page_magic, storage_path, page_count
                    )
                    return gallery_id, has_issue

            try:
                while True:
                    if getattr(settings, "global_paused", False):
                        break

                    async with app_state.session_factory() as session:
                        repo = GalleryRepository(session)
                        batch = await repo.list_magic_scan_targets(after_id=after_id, limit=200)

                    if not batch:
                        break

                    after_id = batch[-1].id
                    scanned = int(tracker.get("scanned", 0) or 0)
                    tracker.update(total=scanned + len(batch))

                    tasks = [
                        _scan_one(
                            g.id,
                            getattr(g, "storage_path", "") or "",
                            int(getattr(g, "page_count", 0) or 0),
                        )
                        for g in batch
                    ]
                    results = await asyncio.gather(*tasks)

                    corrupt_ids = list(tracker.get("corrupt_ids") or [])
                    for gid, has_issue in results:
                        scanned += 1
                        if has_issue:
                            corrupt_ids.append(gid)
                    tracker.update(scanned=scanned, corrupt_ids=corrupt_ids)

            except asyncio.CancelledError:
                tracker.update(last_error="cancelled")
                logger.info("integrity magic scan cancelled", extra=log_extra(scanned=tracker.get("scanned")))
                raise
            except Exception as exc:
                tracker.update(last_error=type(exc).__name__)
                logger.exception(
                    "integrity magic scan error",
                    extra=log_extra(error=type(exc).__name__, message=str(exc)),
                )
