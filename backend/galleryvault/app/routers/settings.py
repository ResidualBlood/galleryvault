"""Settings endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse

from ...config import normalize_library_roots
from ...db.models import FavoritesMonitor
from ...db.repository import FavoritesRepository, GalleryRepository, SettingsRepository
from ...logging import (
    clear_recent_logs,
    get_log_file_path,
    get_log_level,
    get_recent_logs,
    set_log_level,
)
from ...secrets import encrypt, encrypt_json, encryption_enabled, is_encrypted
from ...services.settings_service import (
    decrypt_user_settings,
    is_public_site,
    refresh_services,
    settings_public,
    update_runtime_settings,
)
from ..dependencies import (
    db_error,
    display_title,
    get_current_settings,
    get_eh_client,
    get_session,
    spawn_task,
)
from ..schemas import LogLevelRequest, SavedSearchRequest, SettingsRequest
from ..state import app_state

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/settings")
async def settings_get() -> dict[str, object]:
    try:
        async for session in get_session():
            persisted = await SettingsRepository(session).get()
            persisted = decrypt_user_settings(persisted)
            update_runtime_settings(persisted)
            break
    except Exception as exc:  # noqa: BLE001
        logger.warning("settings could not be re-read", extra={"error": str(exc)})
    return settings_public()


@router.post("/api/settings")
async def settings_save(body: SettingsRequest) -> dict[str, object]:
    return await _save_settings(body)


@router.get("/api/settings/cookie-health")
async def settings_cookie_health() -> dict[str, object]:
    from ...services.eh_client import probe_cookie_health

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


async def _save_settings(body: SettingsRequest) -> dict[str, object]:
    values = body.model_dump(exclude_none=True)
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
        async for session in get_session():
            db_settings = await SettingsRepository(session).get()
            break
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
        async for session in get_session():
            async with session.begin():
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
            break
    except Exception as exc:
        raise db_error(exc) from exc

    old_base = str(db_settings.get("exhentai_base_url") or "")
    new_base = str(persisted_values.get("exhentai_base_url") or "")
    if is_public_site(old_base) and not is_public_site(new_base):
        try:
            async for session in get_session():
                async with session.begin():
                    resumed = await GalleryRepository(session).resume_not_visible()
                if resumed:
                    logger.info("resumed tag sync for not-visible galleries", extra={"count": resumed})
                break
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not resume not-visible galleries", extra={"error": str(exc)})
    await refresh_services()
    from ...services.eh_client import probe_cookie_health

    spawn_task(probe_cookie_health(), "cookie health probe after settings save")
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

    if log_path and log_path.exists() and log_path.is_file():
        return FileResponse(
            str(log_path),
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
        ctx_str = " ".join(f"{k}={v!r}" for k, v in it.get("context", {}).items())
        line = f"{it.get('time')} {it.get('level', 'INFO'):<8} {it.get('logger', 'app')}: {it.get('message')}"
        if ctx_str:
            line += f" [{ctx_str}]"
        if it.get("exception"):
            line += f"\n{it.get('exception')}"
        lines.append(line)
    content = "\n".join(lines) + "\n"
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
    )


_SAVED_SEARCH_MAX = 30


async def _user_settings() -> dict:
    async for session in get_session():
        return await SettingsRepository(session).get()
    return {}


async def _merge_user_settings(updates: dict) -> dict:
    async for session in get_session():
        async with session.begin():
            repo = SettingsRepository(session)
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
async def saved_searches_list() -> dict[str, object]:
    try:
        stored = await _user_settings()
    except Exception as exc:  # noqa: BLE001
        logger.warning("saved searches read failed", extra={"error": str(exc)})
        stored = {}
    items = _normalize_saved_searches(stored.get("saved_searches"))
    return {"items": items}


@router.post("/api/saved-searches")
async def saved_searches_add(body: SavedSearchRequest) -> dict[str, object]:
    import uuid

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        stored = await _user_settings()
        items = _normalize_saved_searches(stored.get("saved_searches"))
        if len(items) >= _SAVED_SEARCH_MAX:
            raise HTTPException(status_code=409, detail="saved search limit reached")
        entry = {"id": uuid.uuid4().hex, "name": name, "query": body.query or {}}
        items.append(entry)
        await _merge_user_settings({"saved_searches": items})
    except HTTPException:
        raise
    except Exception as exc:
        raise db_error(exc) from exc
    return entry


@router.delete("/api/saved-searches/{search_id}")
async def saved_searches_delete(search_id: str) -> dict[str, object]:
    try:
        stored = await _user_settings()
        items = _normalize_saved_searches(stored.get("saved_searches"))
        next_items = [it for it in items if it.get("id") != search_id]
        if len(next_items) == len(items):
            raise HTTPException(status_code=404, detail="saved search not found")
        await _merge_user_settings({"saved_searches": next_items})
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
    from pathlib import Path

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


@router.get("/api/system/storage")
async def system_storage() -> dict[str, object]:
    from pathlib import Path

    from ...services.storage_usage import storage_tracker

    settings = get_current_settings()
    cache_root = Path(settings.thumbnail_cache_dir).parent
    library_bytes = 0
    largest: list[dict[str, object]] = []
    try:
        async for session in get_session():
            repo = GalleryRepository(session)
            library_bytes = await repo.library_storage_sum()
            rows = await repo.largest_by_storage(10)
            largest = [
                {
                    "id": row.id,
                    "title": display_title(row),
                    "storage_size": row.storage_size or row.file_size or 0,
                }
                for row in rows
            ]
            break
    except Exception as exc:  # noqa: BLE001
        logger.warning("storage dashboard db failed", extra={"error": str(exc)})

    # Ensure background calibration is initiated if not already running and no snapshot exists
    dl_snap = storage_tracker.get_downloads_snapshot()
    c_snap = storage_tracker.get_cache_snapshot()
    if dl_snap.bytes is None or c_snap.bytes is None:
        storage_tracker.trigger_calibration(settings.download_root, cache_root)

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
    lib_path = (settings.library_roots or [None])[0]
    library = _path_info(lib_path, bytes_value=library_bytes)
    return {
        "library": library,
        "downloads": downloads,
        "cache": cache,
        "largest": largest,
    }

