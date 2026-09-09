"""Settings endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import normalize_library_roots
from ...db.models import FavoritesMonitor, Gallery
from ...db.repository import FavoritesRepository, GalleryRepository, SettingsRepository
from ...db.session import safe_transaction
from ...logging import (
    clear_recent_logs,
    get_log_file_path,
    get_log_level,
    get_log_root,
    get_recent_logs,
    mask_sensitive,
    set_log_level,
)
from ...secrets import encrypt, encrypt_json, encryption_enabled, is_encrypted
from ...services.eh_client import probe_cookie_health
from ...services.settings_service import (
    SettingsService,
    is_public_site,
    refresh_services,
    settings_public,
    update_runtime_settings,
)
from ..core.task_dispatcher import TaskDispatcher
from ..core.uow import UnitOfWork
from ..dependencies import (
    db_error,
    display_title,
    get_current_settings,
    get_eh_client,
    get_session,
    get_task_dispatcher,
    get_task_manager,
    get_unit_of_work,
    resolve_session,
    spawn_task,
)
from ..schemas import LogLevelRequest, SavedSearchRequest, SettingsRequest
from ..state import app_state

logger = logging.getLogger(__name__)
router = APIRouter()

__all__ = ["router", "spawn_task"]

_SAVED_SEARCH_MAX = 30


def get_settings_service(
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
) -> SettingsService:
    return SettingsService(uow=uow, task_dispatcher=dispatcher)


def _resolve_dispatcher(dispatcher: Any) -> TaskDispatcher:
    if isinstance(dispatcher, TaskDispatcher):
        return dispatcher
    return get_task_dispatcher()


@router.get("/api/settings")
async def settings_get(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    service: SettingsService = Depends(get_settings_service),  # noqa: B008
) -> dict[str, object]:
    try:
        persisted = await service.get_persisted_settings()
        update_runtime_settings(persisted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("settings could not be re-read", extra={"error": str(exc)})
    return service.get_public_settings()


@router.post("/api/settings")
async def settings_save(
    body: SettingsRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    disp = _resolve_dispatcher(dispatcher)
    return await _save_settings(body, session=session, dispatcher=disp)


@router.get("/api/settings/cookie-health")
async def settings_cookie_health() -> dict[str, object]:
    health = app_state.extra.get("cookie_health")
    stale = True
    if isinstance(health, dict) and health.get("checked_at"):
        try:
            age = (
                datetime.now(UTC) - datetime.fromisoformat(str(health["checked_at"]))
            ).total_seconds()
            stale = age > 600
        except Exception:  # noqa: BLE001
            stale = True
    if health is None or stale:
        health = await probe_cookie_health()
    return health


@router.post("/api/settings/exhentai/test")
async def settings_test_exhentai() -> JSONResponse:
    settings = get_current_settings()
    if not settings.exhentai_cookies:
        health = {
            "state": "not_configured",
            "detail": "ExHentai Cookie 未设置",
            "checked_at": datetime.now(UTC).isoformat(),
        }
        app_state.extra["cookie_health"] = health
        return JSONResponse(
            {"status": "not_configured", "message": "ExHentai Cookie 未设置"},
            status_code=400,
        )
    client = get_eh_client()
    state, detail = await client.check_login()
    health = {
        "state": state,
        "detail": detail,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    app_state.extra["cookie_health"] = health
    if state == "ok":
        return JSONResponse({"status": "ok", "message": "登录成功"}, status_code=200)
    if state == "no_exhentai_access":
        return JSONResponse(
            {"status": "failed", "message": f"无法访问里站：缺少有效的 igneous cookie（{detail}）"},
            status_code=403,
        )
    if state == "failed":
        return JSONResponse(
            {"status": "failed", "message": f"ExHentai 请求失败或反爬挑战（{detail}）"},
            status_code=502,
        )
    return JSONResponse(
        {"status": "failed", "message": f"登录失败：cookie 无效或已过期（{detail}）"},
        status_code=401,
    )


async def _save_settings(
    body: SettingsRequest,
    session: AsyncSession | None = None,
    dispatcher: TaskDispatcher | None = None,
) -> dict[str, object]:
    if session is None:
        if not app_state.session_factory:
            raise HTTPException(status_code=503, detail="Database session factory not initialized")
        async with app_state.session_factory() as s:
            return await _save_settings(body, session=s, dispatcher=dispatcher)

    values = body.model_dump(exclude_none=True)
    if "cold_storage_root" in values and isinstance(values["cold_storage_root"], str):
        values["cold_storage_root"] = values["cold_storage_root"].strip()
    if "telegram_bot_token" in values and not str(values["telegram_bot_token"]).strip():
        values.pop("telegram_bot_token", None)
    if values.get("exhentai_base_url"):
        host = (urlparse(str(values["exhentai_base_url"])).hostname or "").lower()
        if host not in {"exhentai.org", "e-hentai.org"} and not host.endswith(
            (".exhentai.org", ".e-hentai.org")
        ):
            raise HTTPException(
                status_code=422, detail="exhentai_base_url must be on exhentai.org / e-hentai.org"
            )
    if "library_roots" in values:
        values["library_roots"] = normalize_library_roots(values["library_roots"])
    for proxy_key in ("http_proxy", "socks5_proxy"):
        if values.get(proxy_key) == "":
            values[proxy_key] = None
    if "favorites" in values:
        favorites = values.pop("favorites")

        def _favcat(item: dict[str, object]) -> int:
            try:
                return int(item.get("favcat", -1))
            except (TypeError, ValueError):
                return -1

        if not isinstance(favorites, list) or any(
            not isinstance(item, dict)
            or _favcat(item) not in range(10)
            or item.get("mode") not in {"monitor_only", "incremental", "force"}
            for item in favorites
        ):
            raise HTTPException(status_code=422, detail="invalid favorites configuration")
        values["favorites_categories"] = [
            _favcat(item) for item in favorites if bool(item.get("enabled", False))
        ]
    else:
        favorites = []
    if "exhentai_cookies" in values:
        values["exhentai_cookies"] = {
            str(key): str(value)
            for key, value in values["exhentai_cookies"].items()
            if str(key) in {"ipb_member_id", "ipb_pass_hash", "igneous"} and str(value)
        }
    cookie_fields = {}
    for key in ("ipb_member_id", "ipb_pass_hash", "igneous"):
        value = values.pop(key, None)
        if value:
            cookie_fields[key] = value
    current_settings = get_current_settings()
    if cookie_fields:
        values["exhentai_cookies"] = {**current_settings.exhentai_cookies, **cookie_fields}
    update_runtime_settings(values)

    db_settings = {}
    try:
        db_settings = await SettingsRepository(session).get()
    except Exception:  # noqa: BLE001
        db_settings = {}

    persisted_values = {**db_settings, **values}
    cookies = persisted_values.get("exhentai_cookies")
    if isinstance(cookies, (dict, list)) and cookies:
        if not encryption_enabled():
            logger.warning(
                "refusing to store exhentai_cookies in plaintext; set ENCRYPTION_KEY to enable encryption"
            )
            raise HTTPException(
                status_code=422,
                detail="encryption not enabled; cannot store ExHentai cookies without encryption",
            )
        persisted_values["exhentai_cookies"] = encrypt_json(cookies)
    token = persisted_values.get("telegram_bot_token")
    if isinstance(token, str) and token and not is_encrypted(token):
        persisted_values["telegram_bot_token"] = encrypt(token)

    try:
        async with safe_transaction(session):
            await SettingsRepository(session).save(persisted_values)
            for item in favorites:
                favcat = _favcat(item)
                row = await FavoritesRepository(session).category(favcat)
                if row is None:
                    row = FavoritesMonitor(favcat=favcat)
                    session.add(row)
                row.enabled = bool(item.get("enabled", False))
                row.mode = str(item["mode"])
                row.poll_interval_seconds = max(
                    60, int(item.get("poll_interval_minutes", 720)) * 60
                )
    except Exception as exc:
        raise db_error(exc) from exc

    old_base = str(db_settings.get("exhentai_base_url") or "")
    new_base = str(persisted_values.get("exhentai_base_url") or "")
    if is_public_site(old_base) and not is_public_site(new_base):
        try:
            async with safe_transaction(session):
                resumed = await GalleryRepository(session).resume_not_visible()
            if resumed:
                logger.info(
                    "resumed tag sync for not-visible galleries", extra={"count": resumed}
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not resume not-visible galleries", extra={"error": str(exc)})
    await refresh_services()

    disp = dispatcher or _resolve_dispatcher(None)
    disp.spawn(probe_cookie_health(), "cookie health probe after settings save")
    return settings_public()


@router.get("/api/system/logs")
async def system_logs_get(
    min_level: str = "INFO", limit: int = 100, search: str | None = None
) -> dict[str, object]:
    """Retrieve recent system logs from the in-memory ring buffer."""
    capped_limit = max(1, min(limit, 500))
    log_path = get_log_file_path()
    file_exists = bool(log_path and log_path.exists() and log_path.is_file())
    return {
        "level": get_log_level(),
        "log_mode": "file" if file_exists else "memory",
        "log_file": str(log_path) if file_exists else None,
        "logs": get_recent_logs(min_level=min_level, limit=capped_limit, search=search),
    }


@router.post("/api/system/logs/level")
async def system_logs_set_level(body: LogLevelRequest) -> dict[str, str]:
    """Dynamically change the active log level without container restart."""
    applied = set_log_level(body.level)
    return {"level": applied}


@router.delete("/api/system/logs")
async def system_logs_clear() -> dict[str, str]:
    """Clear the in-memory ring buffer logs."""
    clear_recent_logs()
    return {"status": "cleared"}


@router.get("/api/system/logs/download")
async def system_logs_download() -> Response:
    """Download the current on-disk system log file or serialize memory ring buffer."""
    log_path = get_log_file_path()
    timestamp_str = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    download_filename = f"galleryvault-{timestamp_str}.log"

    if log_path is not None:
        try:
            resolved = log_path.resolve()
        except (ValueError, OSError):
            raise HTTPException(status_code=404, detail="Log file not found")

        log_root = get_log_root()
        if log_root is None:
            log_root = log_path.parent.resolve()

        try:
            if not resolved.is_relative_to(log_root):
                raise HTTPException(status_code=403, detail="Log file path outside log directory")
        except (ValueError, TypeError):
            raise HTTPException(status_code=403, detail="Log file path outside log directory")

        if not resolved.exists() or not resolved.is_file():
            raise HTTPException(status_code=404, detail="Log file not found")

        return FileResponse(
            str(resolved),
            media_type="text/plain; charset=utf-8",
            filename=download_filename,
        )

    recent = get_recent_logs(min_level="DEBUG", limit=2000)
    lines: list[str] = [
        f"# [GalleryVault Runtime Logs - In-Memory Fallback - {datetime.now(UTC).isoformat()}]",
        "# (Log file not present on disk; displaying recent memory ring buffer records)",
        "",
    ]
    for it in reversed(recent):
        raw_ctx = it.get("context", {})
        masked_ctx = mask_sensitive(raw_ctx) if isinstance(raw_ctx, dict) else raw_ctx
        ctx_str = (
            " ".join(f"{k}={v!r}" for k, v in masked_ctx.items())
            if isinstance(masked_ctx, dict)
            else ""
        )
        msg = mask_sensitive(str(it.get("message", "")))
        line = f"{it.get('time')} {it.get('level', 'INFO'):<8} {it.get('logger', 'app')}: {msg}"
        if ctx_str:
            line += f" [{ctx_str}]"
        if it.get("exception"):
            exc_str = mask_sensitive(str(it.get("exception")))
            line += f"\n{exc_str}"
        lines.append(line)
    content = mask_sensitive("\n".join(lines) + "\n")
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
    )


async def _user_settings(session: AsyncSession | None = None) -> dict:
    if session is not None:
        return await SettingsRepository(session).get()
    if app_state.session_factory:
        async with app_state.session_factory() as s:
            return await SettingsRepository(s).get()
    return {}


async def _merge_user_settings(updates: dict, session: AsyncSession | None = None) -> dict:
    if session is not None:
        async with safe_transaction(session):
            repo = SettingsRepository(session)
            existing = await repo.get()
            merged = {**existing, **updates}
            await repo.save(merged)
            return merged
    if app_state.session_factory:
        async with app_state.session_factory() as s, safe_transaction(s):
            repo = SettingsRepository(s)
            existing = await repo.get()
            merged = {**existing, **updates}
            await repo.save(merged)
            return merged
    return updates


def _normalize_saved_searches(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        query = item.get("query") if isinstance(item.get("query"), dict) else {}
        ident = str(item.get("id") or "").strip()
        if not name:
            continue
        out.append({"id": ident, "name": name, "query": query})
    return out[:_SAVED_SEARCH_MAX]


@router.get("/api/saved-searches")
async def saved_searches_list(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        stored = await _user_settings(session=session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("saved searches read failed", extra={"error": str(exc)})
        stored = {}
    items = _normalize_saved_searches(stored.get("saved_searches"))
    return {"items": items}


@router.post("/api/saved-searches")
async def saved_searches_add(
    body: SavedSearchRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        stored = await _user_settings(session=session)
        items = _normalize_saved_searches(stored.get("saved_searches"))
        if len(items) >= _SAVED_SEARCH_MAX:
            raise HTTPException(status_code=409, detail="saved search limit reached")
        entry = {"id": uuid.uuid4().hex, "name": name, "query": body.query or {}}
        items.append(entry)
        await _merge_user_settings({"saved_searches": items}, session=session)
    except HTTPException:
        raise
    except Exception as exc:
        raise db_error(exc) from exc
    return entry


@router.delete("/api/saved-searches/{search_id}")
async def saved_searches_delete(
    search_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        stored = await _user_settings(session=session)
        items = _normalize_saved_searches(stored.get("saved_searches"))
        next_items = [it for it in items if it.get("id") != search_id]
        if len(next_items) == len(items):
            raise HTTPException(status_code=404, detail="saved search not found")
        await _merge_user_settings({"saved_searches": next_items}, session=session)
    except HTTPException:
        raise
    except Exception as exc:
        raise db_error(exc) from exc
    return {"deleted": True, "id": search_id}


def _path_info(
    path: object,
    bytes_value: int | None = None,
    computed_at: float | None = None,
    stale: bool = False,
    computing: bool = False,
) -> dict[str, object]:
    import shutil

    root = Path(str(path)) if path else Path()
    exists = bool(path) and root.exists()
    info: dict[str, object] = {
        "path": str(root) if path else "",
        "bytes": bytes_value,
        "exists": exists,
        "computed_at": computed_at,
        "stale": stale,
        "computing": computing,
    }
    if exists:
        try:
            usage = shutil.disk_usage(root)
            info["disk_total"] = int(usage.total)
            info["disk_used"] = int(usage.used)
            info["disk_free"] = int(usage.free)
        except OSError:
            pass
    return info


async def _query_storage_aggregates(
    session: AsyncSession, cold_root: str
) -> tuple[int, int, int, int, int]:
    cold_galleries = 0
    cold_images = 0
    cold_bytes = 0
    library_galleries = 0
    library_images = 0

    valid_cond = (Gallery.expunged.is_(False), Gallery.trashed.is_(False))
    if cold_root:
        size_col = func.coalesce(Gallery.storage_size, Gallery.file_size)
        cold_stmt = select(
            func.count(Gallery.id),
            func.coalesce(func.sum(Gallery.page_count), 0),
            func.coalesce(func.sum(size_col), 0),
        ).where(
            *valid_cond,
            Gallery.storage_path.startswith(cold_root),
        )
        cold_row = (await session.execute(cold_stmt)).first()
        if cold_row:
            cold_galleries = int(cold_row[0] or 0)
            cold_images = int(cold_row[1] or 0)
            cold_bytes = int(cold_row[2] or 0)

        lib_stmt = select(
            func.count(Gallery.id),
            func.coalesce(func.sum(Gallery.page_count), 0),
        ).where(
            *valid_cond,
            Gallery.storage_path.is_(None)
            | not_(Gallery.storage_path.startswith(cold_root)),
        )
        lib_row = (await session.execute(lib_stmt)).first()
        if lib_row:
            library_galleries = int(lib_row[0] or 0)
            library_images = int(lib_row[1] or 0)
    else:
        lib_stmt = select(
            func.count(Gallery.id),
            func.coalesce(func.sum(Gallery.page_count), 0),
        ).where(*valid_cond)
        lib_row = (await session.execute(lib_stmt)).first()
        if lib_row:
            library_galleries = int(lib_row[0] or 0)
            library_images = int(lib_row[1] or 0)

    return cold_galleries, cold_images, cold_bytes, library_galleries, library_images


@router.get("/api/system/storage")
async def system_storage(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    from ...services.storage_usage import storage_tracker

    settings = get_current_settings()
    cache_root = Path(settings.thumbnail_cache_dir).parent
    cold_root = (getattr(settings, "cold_storage_root", None) or "").strip()
    library_bytes = 0
    cold_bytes = 0
    library_galleries = 0
    library_images = 0
    cold_galleries = 0
    cold_images = 0
    largest: list[dict[str, object]] = []

    try:
        repo = GalleryRepository(session)
        library_bytes = await repo.library_storage_sum()
        (
            cold_galleries,
            cold_images,
            cold_bytes,
            library_galleries,
            library_images,
        ) = await _query_storage_aggregates(session, cold_root)

        rows = await repo.largest_by_storage(10)
        largest = [
            {
                "id": row.id,
                "title": display_title(row),
                "storage_size": row.storage_size or row.file_size or 0,
                "file_count": row.page_count or 0,
            }
            for row in rows
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("storage dashboard db failed", extra={"error": str(exc)})

    # Ensure background calibration is initiated if not already running and no snapshot exists
    lib_path = (settings.library_roots or [None])[0]
    dl_snap = storage_tracker.get_downloads_snapshot()
    c_snap = storage_tracker.get_cache_snapshot()
    l_snap = storage_tracker.get_library_snapshot()
    if dl_snap.bytes is None or c_snap.bytes is None or (lib_path and l_snap.bytes is None):
        storage_tracker.trigger_calibration(
            settings.download_root, cache_root, library_root=lib_path
        )

    downloads = _path_info(
        settings.download_root,
        bytes_value=dl_snap.bytes,
        computed_at=dl_snap.computed_at,
        stale=dl_snap.stale,
        computing=dl_snap.computing,
    )
    cache = _path_info(
        str(cache_root),
        bytes_value=c_snap.bytes,
        computed_at=c_snap.computed_at,
        stale=c_snap.stale,
        computing=c_snap.computing,
    )
    lib_val = (
        l_snap.bytes if l_snap.bytes is not None else (None if l_snap.computing else library_bytes)
    )
    library = _path_info(
        lib_path,
        bytes_value=lib_val,
        computed_at=l_snap.computed_at,
        stale=l_snap.stale,
        computing=l_snap.computing,
    )
    cold = _path_info(cold_root, bytes_value=cold_bytes)
    cache_thumbs = library_images + cold_images
    library["gallery_count"] = library_galleries
    library["image_count"] = library_images
    cold["gallery_count"] = cold_galleries
    cold["image_count"] = cold_images
    cache["thumbnail_count"] = cache_thumbs
    return {
        "library": library,
        "cold": cold,
        "downloads": downloads,
        "cache": cache,
        "largest": largest,
    }


@router.post("/api/system/purge-archived-sources", status_code=202)
async def purge_archived_sources(
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
) -> dict[str, object]:
    """Purge leftover source directories for galleries already archived to cold storage."""
    from ...services.cold_archive import run_purge_archived_sources

    disp = _resolve_dispatcher(dispatcher)
    tm = disp.task_manager if getattr(disp, "task_manager", None) is not None else get_task_manager()
    state = tm._resolve_task_state("purge-archived-sources")
    if state.get("running"):
        return {"status": "running"}

    disp.spawn(run_purge_archived_sources(tm), "purge archived sources")
    return {"status": "started"}
