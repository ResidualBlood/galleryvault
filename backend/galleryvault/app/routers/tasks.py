"""Background-task endpoints: scan, activity log, tag-sync, thumbnails."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from ...db.repository import BackgroundJobsRepository, GalleryRepository
from ...services.scan_worker import run_scan
from ...services.tag_sync_worker import category_refresh_once, enqueue_tag_sync, jobs_count
from ...services.thumbnail_worker import seed_thumbnails
from ..dependencies import get_session, get_task_manager, spawn_task

router = APIRouter()


async def _clear_jobs(job_type: str) -> None:
    async for session in get_session():
        async with session.begin():
            await BackgroundJobsRepository(session).clear(job_type)
        break


@router.post("/api/scan", status_code=202)
async def trigger_scan() -> dict[str, object]:
    tm = get_task_manager()
    if not tm.scan_state["running"]:
        tm.scan_state["running"] = True
        spawn_task(run_scan(), "library scan")
    return {"status": "running" if tm.scan_state["running"] else "started"}


@router.get("/api/scan")
async def scan_status() -> dict[str, object]:
    tm = get_task_manager()
    return tm.scan_state.copy()


@router.get("/api/logs")
async def background_task_logs() -> dict[str, object]:
    """Aggregate live background tasks and the recent activity log."""
    tm = get_task_manager()
    return {"running": tm.get_running_summary(), "finished": list(tm.task_history)}


@router.post("/api/logs/{task}/cancel", status_code=202)
async def cancel_background_task(task: str) -> dict[str, object]:
    task_key = "metadata" if task in {"metadata", "metadata-sync"} else task
    if task_key not in {"scan", "tag-sync", "thumbs", "metadata"}:
        raise HTTPException(status_code=404, detail="Unknown task")
    tm = get_task_manager()
    tm.request_cancel(task_key)
    if task_key == "tag-sync":
        await _clear_jobs("tag-sync")
    elif task_key == "thumbs":
        await _clear_jobs("thumbs")
    return {"task": task_key, "status": "cancelling"}


@router.get("/api/tag-sync/status")
async def tag_sync_status() -> dict[str, object]:
    tm = get_task_manager()
    return dict(tm.tag_sync_state)


@router.post("/api/tag-sync/refresh-categories", status_code=202)
async def trigger_category_refresh() -> dict[str, object]:
    """Start a one-time 大分类 backfill for galleries stuck in ``other``."""
    tm = get_task_manager()
    if not tm.tag_sync_state.get("category_refresh_running"):
        spawn_task(category_refresh_once(), "category refresh")
    return {
        "status": "running" if tm.tag_sync_state.get("category_refresh_running") else "started"
    }


@router.get("/api/thumbs/status")
async def thumb_status() -> dict[str, object]:
    tm = get_task_manager()
    return dict(tm.thumb_state)


@router.post("/api/thumbs/generate", status_code=202)
async def trigger_thumbnail_generation() -> dict[str, object]:
    """Queue every gallery missing thumbnails for background generation."""
    tm = get_task_manager()
    await seed_thumbnails()
    queued = await jobs_count("thumb")
    tm.thumb_state["running"] = True
    if queued == 0 and not tm.thumb_state.get("started_at"):
        now = datetime.now(UTC).isoformat()
        tm.record_task("thumbs", now, now, "success", reason="ok 0 / fail 0", done=0, total=0)
    return {"status": "running" if queued else "started", "queued": queued}


@router.post("/api/tag-sync/start", status_code=202)
async def trigger_tag_sync() -> dict[str, object]:
    """Re-queue every gallery that still needs tag sync (manual full run)."""
    tm = get_task_manager()
    async for session in get_session():
        last_id = 0
        seeded = 0
        while True:
            ids = await GalleryRepository(session).pending_tag_sync_ids(1000, last_id)
            if not ids:
                break
            await enqueue_tag_sync(ids)
            seeded += len(ids)
            last_id = ids[-1]
        break

    if seeded == 0 and not tm.tag_sync_state.get("running"):
        now = datetime.now(UTC).isoformat()
        tm.record_task(
            "tag-sync",
            now,
            now,
            "success",
            reason=(
                f"ok {tm.tag_sync_state.get('succeeded', 0)} "
                f"/ fail {tm.tag_sync_state.get('failed', 0)}"
            ),
            done=int(tm.tag_sync_state.get("processed") or 0),
            total=int(tm.tag_sync_state.get("total") or 0),
        )
    return {"status": "started", "queued": seeded}
