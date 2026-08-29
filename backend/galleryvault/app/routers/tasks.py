"""Background-task endpoints: scan, activity log, tag-sync, thumbnails.

Route handlers live here; the shared task state, workers and helpers stay on
``galleryvault.app.main`` (accessed via ``main.X`` at call time so the test
suite's ``monkeypatch.setattr(main, ...)`` still takes effect).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from galleryvault.app import main
from galleryvault.db.repository import BackgroundJobsRepository, GalleryRepository

router = APIRouter()


async def _clear_jobs(job_type: str) -> None:
    async with main._settings_session() as session, session.begin():
        await BackgroundJobsRepository(session).clear(job_type)


@router.post("/api/scan", status_code=202)
async def trigger_scan() -> dict[str, object]:
    if not main.scan_state["running"]:
        main.scan_state["running"] = True
        main._spawn(main._run_scan(), "library scan")
    return {"status": "running" if main.scan_state["running"] else "started"}


@router.get("/api/scan")
async def scan_status() -> dict[str, object]:
    return main.scan_state.copy()


@router.get("/api/logs")
async def background_task_logs() -> dict[str, object]:
    """Aggregate live background tasks and the recent activity log."""
    scan_state = main.scan_state
    tag_sync_state = main.tag_sync_state
    thumb_state = main.thumb_state
    metadata_sync_state = main.metadata_sync_state
    favorites_check_state = main.favorites_check_state
    translation_state = main.translation_state
    running: list[dict[str, object]] = []
    if scan_state["running"]:
        running.append(
            {
                "task": "scan",
                "started_at": scan_state.get("started_at"),
                "done": int(scan_state.get("scanned") or 0),
                "total": None,
                "stage": None,
                "cancellable": True,
            }
        )
    if tag_sync_state["running"]:
        running.append(
            {
                "task": "tag-sync",
                "started_at": tag_sync_state.get("started_at"),
                "done": int(tag_sync_state.get("processed") or 0),
                "total": int(tag_sync_state.get("total") or 0),
                "stage": None,
                "cancellable": True,
            }
        )
    if thumb_state["running"]:
        running.append(
            {
                "task": "thumbs",
                "started_at": thumb_state.get("started_at"),
                "done": int(thumb_state.get("succeeded") or 0)
                + int(thumb_state.get("failed") or 0),
                "total": int(thumb_state.get("total") or 0),
                "stage": None,
                "cancellable": True,
            }
        )
    if metadata_sync_state["running"]:
        running.append(
            {
                "task": "metadata",
                "started_at": metadata_sync_state.get("started_at"),
                "done": int(metadata_sync_state.get("done") or 0),
                "total": int(metadata_sync_state.get("total") or 0),
                "stage": metadata_sync_state.get("stage"),
                "cancellable": True,
            }
        )
    if favorites_check_state["running"]:
        running.append(
            {
                "task": "favcheck",
                "started_at": favorites_check_state.get("started_at"),
                "done": sum(
                    int(item.get("done") or 0)
                    for item in favorites_check_state.get("categories", {}).values()
                    if isinstance(item, dict)
                ),
                "total": sum(
                    int(item.get("total") or 0)
                    for item in favorites_check_state.get("categories", {}).values()
                    if isinstance(item, dict)
                ),
                "stage": None,
                "cancellable": False,
            }
        )
    if translation_state["running"]:
        running.append(
            {
                "task": "translation",
                "started_at": translation_state.get("started_at"),
                "done": int(translation_state.get("entries") or 0),
                "total": None,
                "stage": None,
                "cancellable": False,
            }
        )
    return {"running": running, "finished": list(main.task_history)}


@router.post("/api/logs/{task}/cancel", status_code=202)
async def cancel_background_task(task: str) -> dict[str, object]:
    if task not in {"scan", "tag-sync", "thumbs", "metadata"}:
        raise HTTPException(status_code=404, detail="Unknown task")
    main._request_cancel(task)
    if task == "tag-sync":
        await _clear_jobs("tag-sync")
    elif task == "thumbs":
        await _clear_jobs("thumbs")
    return {"task": task, "status": "cancelling"}


@router.get("/api/tag-sync/status")
async def tag_sync_status() -> dict[str, object]:
    return dict(main.tag_sync_state)


@router.post("/api/tag-sync/refresh-categories", status_code=202)
async def trigger_category_refresh() -> dict[str, object]:
    """Start a one-time 大分类 backfill for galleries stuck in ``other``."""
    if not main.tag_sync_state["category_refresh_running"]:
        main._spawn(main._category_refresh_once(), "category refresh")
    return {
        "status": "running" if main.tag_sync_state["category_refresh_running"] else "started"
    }


@router.get("/api/thumbs/status")
async def thumb_status() -> dict[str, object]:
    return dict(main.thumb_state)


@router.post("/api/thumbs/generate", status_code=202)
async def trigger_thumbnail_generation() -> dict[str, object]:
    """Queue every gallery missing thumbnails for background generation."""
    await main._seed_thumbnails()
    queued = await main._jobs_count("thumb")
    main.thumb_state["running"] = True
    # Nothing to do: record a no-op completion so the manual trigger still shows
    # up in the activity log instead of silently doing nothing.
    if queued == 0 and not main.thumb_state.get("started_at"):
        now = datetime.now(UTC).isoformat()
        main._record_task("thumbs", now, now, "success", reason="ok 0 / fail 0", done=0, total=0)
    return {"status": "running" if queued else "started", "queued": queued}


@router.post("/api/tag-sync/start", status_code=202)
async def trigger_tag_sync() -> dict[str, object]:
    """Re-queue every gallery that still needs tag sync (manual full run)."""
    async with main._settings_session() as session:
        last_id = 0
        seeded = 0
        while True:
            ids = await GalleryRepository(session).pending_tag_sync_ids(1000, last_id)
            if not ids:
                break
            await main._enqueue_tag_sync(ids)
            seeded += len(ids)
            last_id = ids[-1]
    # Nothing was queued: record a no-op completion so the manual trigger is
    # still visible in the activity log.
    if seeded == 0 and not main.tag_sync_state["running"]:
        now = datetime.now(UTC).isoformat()
        main._record_task(
            "tag-sync",
            now,
            now,
            "success",
            reason=(
                f"ok {main.tag_sync_state.get('succeeded', 0)} "
                f"/ fail {main.tag_sync_state.get('failed', 0)}"
            ),
            done=int(main.tag_sync_state.get("processed") or 0),
            total=int(main.tag_sync_state.get("total") or 0),
        )
    return {"status": "started", "queued": seeded}
