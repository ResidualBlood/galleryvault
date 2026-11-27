"""Background-task endpoints: scan, activity log, tag-sync, thumbnails."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...db.repositories.settings import patch_settings
from ...db.repository import BackgroundJobsRepository, GalleryRepository, SettingsRepository
from ...db.session import safe_transaction
from ...services import quota as quota_service
from ...services import tasks as tasks_service
from ...services.cold_archive import run_cold_archive, run_unarchive
from ...services.scan_worker import run_scan
from ...services.settings_service import update_runtime_settings
from ...services.tag_sync_worker import category_refresh_once, enqueue_tag_sync, jobs_count
from ...services.thumbnail_worker import seed_thumbnails
from ..dependencies import get_session, get_task_manager, resolve_session, spawn_task
from ..schemas import QuotaResponse
from ..state import app_state

router = APIRouter()
logger = logging.getLogger(__name__)


# Guard so repeated /api/tag-sync/start clicks do not run concurrent seed passes.
_tag_sync_seed_state: dict[str, bool] = {"running": False}


_TASK_STATE_ATTRS = {
    "scan": "scan_state",
    "archive": "archive_state",
    "unarchive": "unarchive_state",
}


def _begin_task(tm: object, name: str, *, cancellable: bool = False) -> None:
    """Use the manager lifecycle method, tolerating legacy test doubles.

    Production always has ``TaskManager.begin_task``; a few router unit tests
    pass a minimal fake that only exposes the state dict.
    """
    begin = getattr(tm, "begin_task", None)
    if callable(begin):
        begin(name, cancellable=cancellable)
        return
    state = getattr(tm, _TASK_STATE_ATTRS[name], None)
    if isinstance(state, dict):
        state["running"] = True


async def _clear_jobs(job_type: str) -> None:
    if not app_state.session_factory:
        return
    async with app_state.session_factory() as session, safe_transaction(session):
        await BackgroundJobsRepository(session).clear(job_type)


@router.get("/api/pause")
async def get_pause() -> dict[str, object]:
    settings = app_state.settings or get_settings()
    return {"paused": bool(getattr(settings, "global_paused", False))}


@router.post("/api/pause", status_code=200)
async def set_pause(
    body: dict, session: AsyncSession = Depends(get_session)  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    # Accept {"paused": bool} or {"global_paused": bool}
    if "paused" in body:
        paused = bool(body["paused"])
    elif "global_paused" in body:
        paused = bool(body["global_paused"])
    else:
        from fastapi import HTTPException as _HTTPException

        raise _HTTPException(status_code=422, detail="paused is required")
    settings = app_state.settings or get_settings()
    new_settings = settings.model_copy(update={"global_paused": paused})
    app_state.settings = new_settings
    update_runtime_settings({"global_paused": paused})
    try:
        async with safe_transaction(session):
            await patch_settings(SettingsRepository(session), {"global_paused": paused})
    except Exception as exc:
        from ..dependencies import db_error

        raise db_error(exc) from exc
    # Mirror to telegram bot in-memory flag if running
    try:

        # No direct global bot reference; app_state.telegram holds notifier, not bot service
        # But bot service's paused is now backed by global_paused, so nothing to do
        pass
    except Exception:  # noqa: BLE001, S110
        pass
    return {"paused": paused}


@router.get("/api/quota", response_model=QuotaResponse)
async def get_quota() -> dict[str, object]:
    """Cached GP balance + Image Limits (thin wrapper over ``services.quota``)."""
    return await quota_service.get_quota()


@router.post("/api/scan", status_code=202)
async def trigger_scan() -> dict[str, object]:
    settings = app_state.settings or get_settings()
    if getattr(settings, "global_paused", False):
        return {"status": "paused", "detail": "Global paused: scan is disabled"}
    tm = get_task_manager()
    if not tm.scan_state["running"]:
        _begin_task(tm, "scan", cancellable=True)
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
    finished = await tm.history_records()
    return {"running": tm.get_running_summary(), "finished": finished}


@router.post("/api/logs/{task}/cancel", status_code=202)
async def cancel_background_task(task: str) -> dict[str, object]:
    """Thin wrapper over ``services.tasks.cancel_background_task``."""
    return await tasks_service.cancel_background_task(
        task,
        manager=get_task_manager(),
        clear_jobs=_clear_jobs,
        tag_sync_seeding=_tag_sync_seed_state["running"],
    )


@router.get("/api/archive")
async def archive_status() -> dict[str, object]:
    tm = get_task_manager()
    return dict(tm.archive_state)


class ArchiveRestoreRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


@router.post("/api/archive/restore", status_code=202)
async def restore_archive(body: ArchiveRestoreRequest) -> dict[str, object]:
    """Move the given cold galleries back to the download root."""
    ids = list(dict.fromkeys(int(gid) for gid in body.ids if int(gid) > 0))
    if not ids:
        raise HTTPException(status_code=422, detail="ids is required")
    settings = app_state.settings or get_settings()
    if getattr(settings, "global_paused", False):
        return {"status": "paused", "detail": "Global paused: unarchive is disabled"}
    tm = get_task_manager()
    if tm.unarchive_state.get("running"):
        return {"status": "running", "total": len(ids)}
    tm.clear_cancelled("unarchive")
    _begin_task(tm, "unarchive", cancellable=True)
    spawn_task(run_unarchive(ids), "cold unarchive")
    return {"status": "started", "total": len(ids)}


@router.post("/api/archive", status_code=202)
async def trigger_archive() -> dict[str, object]:
    settings = app_state.settings or get_settings()
    cold_root = (getattr(settings, "cold_storage_root", None) or "").strip()
    if not cold_root:
        raise HTTPException(status_code=422, detail="Cold storage root is not configured")
    if getattr(settings, "global_paused", False):
        return {"status": "paused", "detail": "Global paused: archive is disabled"}
    tm = get_task_manager()
    if tm.archive_state.get("running"):
        return {"status": "running"}
    tm.clear_cancelled("archive")
    _begin_task(tm, "archive", cancellable=True)
    spawn_task(run_cold_archive(), "cold archive")
    return {"status": "started"}


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


@router.post("/api/tag-sync/repair-categories")
async def repair_categories(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    """One-click local repair for galleries stuck in misc/other using cached metadata."""
    session = await resolve_session(session, fallback_dep=get_session)
    count = await GalleryRepository(session).sync_categories_from_metadata()
    return {"status": "ok", "repaired": count}


@router.get("/api/thumbs/status")
async def thumb_status() -> dict[str, object]:
    tm = get_task_manager()
    return dict(tm.thumb_state)


@router.post("/api/thumbs/generate", status_code=202)
async def trigger_thumbnail_generation() -> dict[str, object]:
    """Queue every gallery missing thumbnails for background generation."""
    tm = get_task_manager()
    # A previous run may have been cancelled and left its marker behind.
    tm.clear_cancelled("thumbs")
    if tm.thumb_state.get("seeding"):
        return {"status": "running", "message": "Thumbnail seeding already in progress"}
    tm.thumb_state["seeding"] = True
    # Thumbs are driven by the job queue, so open the ledger row here; the
    # worker (or the empty-seed branch below) closes it with ``record_task``.
    await tm.begin_persisted_task("thumbs", cancellable=True)

    async def _run_seed() -> None:
        try:
            await seed_thumbnails()
            queued = await jobs_count("thumb")
            tm.set_task_running("thumbs", bool(queued))
            if queued == 0 and not tm.thumb_state.get("history_recorded"):
                now = datetime.now(UTC).isoformat()
                tm.record_task(
                    "thumbs", now, now, "success", reason="ok 0 / fail 0", done=0, total=0
                )
                tm.thumb_state["history_recorded"] = True
        finally:
            tm.thumb_state["seeding"] = False

    spawn_task(_run_seed(), "thumbnail seeding")
    return {"status": "started"}


async def _seed_pending_tag_sync() -> None:
    """Queue every pending tag-sync id in the background.

    The full table walk used to run inside the HTTP request and could take
    minutes on a large library; it now runs as a background task so the
    endpoint returns immediately.
    """
    session_factory = app_state.session_factory
    if session_factory is None:
        _tag_sync_seed_state["running"] = False
        return
    started_at = datetime.now(UTC).isoformat()
    seeded = 0
    status = "success"
    reason = ""
    try:
        last_id = 0
        while True:
            async with session_factory() as session:
                ids = await GalleryRepository(session).pending_tag_sync_ids(1000, last_id)
            if not ids:
                break
            await enqueue_tag_sync(ids)
            seeded += len(ids)
            last_id = ids[-1]
        reason = f"queued {seeded} pending galleries"
    except Exception as exc:
        status = "failed"
        reason = f"tag sync seeding failed: {type(exc).__name__}"
        raise
    finally:
        _tag_sync_seed_state["running"] = False
        completed_at = datetime.now(UTC).isoformat()
        tm = get_task_manager()
        tm.record_task(
            "tag-sync",
            started_at,
            completed_at,
            status,
            reason=reason,
            done=0,
            total=0,
        )


@router.post("/api/tag-sync/start", status_code=202)
async def trigger_tag_sync() -> dict[str, object]:
    """Re-queue every gallery that still needs tag sync (manual full run)."""
    tm = get_task_manager()
    # A previous run may have been cancelled and left its marker behind.
    tm.clear_cancelled("tag-sync")
    settings = app_state.settings or get_settings()
    if getattr(settings, "global_paused", False):
        return {"status": "paused", "detail": "Global paused: tag sync is disabled"}
    if _tag_sync_seed_state["running"]:
        raise HTTPException(status_code=409, detail="tag sync seeding already running")
    _tag_sync_seed_state["running"] = True
    task = spawn_task(_seed_pending_tag_sync(), "tag sync seeding")
    if task is None:
        _tag_sync_seed_state["running"] = False
        raise HTTPException(status_code=503, detail="background tasks unavailable")
    return {"status": "started", "queued": 0}
