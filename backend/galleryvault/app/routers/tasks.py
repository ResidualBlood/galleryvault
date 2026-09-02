"""Background-task endpoints: scan, activity log, tag-sync, thumbnails."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from ...config import get_settings
from ...db.repository import BackgroundJobsRepository, GalleryRepository, SettingsRepository
from ...services.scan_worker import run_scan
from ...services.settings_service import update_runtime_settings
from ...services.tag_sync_worker import category_refresh_once, enqueue_tag_sync, jobs_count
from ...services.thumbnail_worker import seed_thumbnails
from ..dependencies import get_session, get_task_manager, spawn_task
from ..state import app_state

router = APIRouter()


async def _clear_jobs(job_type: str) -> None:
    async for session in get_session():
        async with session.begin():
            await BackgroundJobsRepository(session).clear(job_type)
        break


@router.get("/api/pause")
async def get_pause() -> dict[str, object]:
    settings = app_state.settings or get_settings()
    return {"paused": bool(getattr(settings, "global_paused", False))}


@router.post("/api/pause", status_code=200)
async def set_pause(body: dict) -> dict[str, object]:
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
        if app_state.session_factory:
            async for session in get_session():
                async with session.begin():
                    existing = await SettingsRepository(session).get()
                    merged = {**existing, "global_paused": paused}
                    await SettingsRepository(session).save(merged)
                break
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


_GP_CACHE_TTL = 1800  # 30 min, same as cookie probe
_GP_LOCK = None


def _get_gp_lock():
    global _GP_LOCK
    if _GP_LOCK is None:
        import asyncio

        _GP_LOCK = asyncio.Lock()
    return _GP_LOCK


@router.get("/api/quota")
async def get_quota() -> dict[str, object]:
    """Cached GP balance + Image Limits (low-frequency, 30 min TTL)."""
    from datetime import UTC, datetime

    settings = app_state.settings or get_settings()
    cache = app_state.extra.get("gp_cache") if isinstance(app_state.extra.get("gp_cache"), dict) else {}
    now = datetime.now(UTC)
    checked_at = cache.get("checked_at")
    # TTL check
    is_stale = True
    if checked_at:
        try:
            age = (now - datetime.fromisoformat(str(checked_at))).total_seconds()
            is_stale = age > _GP_CACHE_TTL
        except Exception:  # noqa: BLE001
            is_stale = True
    if not is_stale and cache.get("balance") is not None:
        return {
            "gp": cache.get("balance"),
            "image_limit": cache.get("image_limit"),
            "image_limits": cache.get("image_limit"),
            "checked_at": cache.get("checked_at"),
            "error": cache.get("error"),
            "cached": True,
        }
    # Need refresh; try to acquire lock without blocking long
    lock = _get_gp_lock()
    if lock.locked():
        # Return stale cache while refresh is in progress
        return {
            "gp": cache.get("balance"),
            "image_limit": cache.get("image_limit"),
            "image_limits": cache.get("image_limit"),
            "checked_at": cache.get("checked_at"),
            "error": cache.get("error"),
            "cached": True,
            "refreshing": True,
        }
    async with lock:
        # Double-check after acquiring
        cache = app_state.extra.get("gp_cache", {}) if isinstance(app_state.extra.get("gp_cache"), dict) else {}
        checked_at = cache.get("checked_at")
        if checked_at:
            try:
                age = (now - datetime.fromisoformat(str(checked_at))).total_seconds()
                if age <= _GP_CACHE_TTL and cache.get("balance") is not None:
                    return {
                        "gp": cache["balance"],
                        "image_limit": cache.get("image_limit"),
                        "image_limits": cache.get("image_limit"),
                        "checked_at": checked_at,
                        "error": cache.get("error"),
                        "cached": True,
                    }
            except Exception:  # noqa: BLE001, S110
                pass
        # Fetch GP + Image Limits (both low-frequency, same cache)
        balance = None
        image_limit = cache.get("image_limit")
        error = None
        try:
            client = app_state.eh_client
            if client is None:
                from ...services.eh_client import EhClient

                async with EhClient(settings, max_concurrency=settings.exhentai_max_concurrency) as tmp:
                    balance = await tmp.fetch_gp_balance()
                    try:
                        image_limit = await tmp.fetch_image_limits()
                    except Exception:  # noqa: BLE001, S110
                        pass
            else:
                balance = await client.fetch_gp_balance()
                try:
                    image_limit = await client.fetch_image_limits()
                except Exception:  # noqa: BLE001, S110
                    pass
        except Exception as exc:  # noqa: BLE001
            error = type(exc).__name__ + ": " + str(exc)[:120]
            # Keep old balance if exists
            balance = cache.get("balance")
            image_limit = cache.get("image_limit")
        new_cache = {
            "balance": balance,
            "image_limit": image_limit,
            "checked_at": datetime.now(UTC).isoformat(),
            "error": error,
        }
        app_state.extra["gp_cache"] = new_cache
        return {
            "gp": balance,
            "image_limit": image_limit,
            "image_limits": image_limit,
            "checked_at": new_cache["checked_at"],
            "error": error,
            "cached": False,
        }


@router.post("/api/scan", status_code=202)
async def trigger_scan() -> dict[str, object]:
    settings = app_state.settings or get_settings()
    if getattr(settings, "global_paused", False):
        return {"status": "paused", "detail": "Global paused: scan is disabled"}
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
