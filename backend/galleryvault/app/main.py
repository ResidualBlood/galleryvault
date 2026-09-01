"""FastAPI application entry point, middleware stack, lifespan management, and wiring."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    DEFAULT_PASSWORD,
    LOGIN_RATE_MAX,
    LOGIN_RATE_WINDOW,
    _login_attempts,
    _login_lock,
    verify_login_password,
    verify_session,
)
from ..auth import (
    client_ip as _client_ip,
)
from ..auth import (
    is_trusted_proxy as _is_trusted_proxy,
)
from ..auth import (
    login_gate as _login_gate,
)
from ..auth import (
    login_succeeded as _login_succeeded,
)
from ..config import Settings, get_settings, normalize_library_roots
from ..db.models import (
    AppConfig,
    FavoriteItem,
    FavoritesMonitor,
    Gallery,
    GalleryPage,
    GalleryTag,
    Tag,
)
from ..db.models import (
    DownloadTask as DownloadTaskModel,
)
from ..db.repository import (
    BackgroundJobsRepository,
    DownloadRepository,
    FavoritesRepository,
    GalleryRepository,
    GalleryUpdatesRepository,
    SettingsRepository,
)
from ..db.session import create_database
from ..logging import configure_logging, log_extra
from ..observability import request_id_middleware
from ..scanners import registry
from ..scanners.base import GalleryMeta, PageInfo
from ..secrets import (
    decrypt_json_or_value,
    decrypt_or_plain,
    encrypt,
    encrypt_json,
    encryption_enabled,
    is_encrypted,
)
from ..services import messages
from ..services.deletion import (
    delete_galleries_local,
)
from ..services.deletion import (
    delete_local_copy as _delete_local_copy,
)
from ..services.deletion import (
    in_scan_roots as _in_scan_roots,
)
from ..services.deletion import (
    prune_merged_stale_pages as _prune_merged_stale_pages,
)
from ..services.deletion import (
    remove_superseded_copy as _remove_superseded_copy,
)
from ..services.download_worker import (
    download_progress as _download_progress,
)
from ..services.download_worker import (
    download_retry_sweep_loop as _download_retry_sweep_loop,
)
from ..services.download_worker import (
    download_worker_loop as _download_worker_loop,
)
from ..services.download_worker import (
    infer_image_quality as _infer_image_quality,
)
from ..services.download_worker import (
    ingest_downloaded_gallery as _ingest_downloaded_gallery,
)
from ..services.download_worker import (
    maybe_scan_after_download as _maybe_scan_after_download,
)
from ..services.download_worker import (
    record_download_notification as _record_download_notification,
)
from ..services.download_worker import (
    retry_backoff as _retry_backoff,
)
from ..services.download_worker import (
    run_download as _run_download,
)
from ..services.download_worker import (
    telegram_flush_loop as _telegram_flush_loop,
)
from ..services.downloader import Downloader, DownloadTask
from ..services.eh_client import EhClient, parse_gallery_url
from ..services.favorites import FavoritesService
from ..services.favorites_worker import (
    FAVORITES_SKIP_LIMIT,
    _fav_counts_cache,
)
from ..services.favorites_worker import (
    FavoriteDownloadQueue as _FavoriteDownloadQueue,
)
from ..services.favorites_worker import (
    FavoritesRepositoryProxy as _FavoritesRepositoryProxy,
)
from ..services.favorites_worker import (
    estimate_cloud_size as _estimate_cloud_size,
)
from ..services.favorites_worker import (
    favorite_counts_cached as _favorite_counts_cached,
)
from ..services.favorites_worker import (
    favorite_size_sync as _favorite_size_sync,
)
from ..services.favorites_worker import (
    favorites_metadata as _favorites_metadata,
)
from ..services.favorites_worker import (
    favorites_poll_loop as _favorites_poll_loop,
)
from ..services.favorites_worker import (
    favorites_skip_decision as _favorites_skip_decision,
)
from ..services.favorites_worker import (
    refresh_favorite_counts as _refresh_favorite_counts,
)
from ..services.favorites_worker import (
    remote_cover_data_batch as _remote_cover_data_batch,
)
from ..services.favorites_worker import (
    run_duplicates_scan as _run_duplicates_scan,
)
from ..services.favorites_worker import (
    run_favorites_check as _run_favorites_check,
)
from ..services.ingest import GalleryIngestService
from ..services.library import LibraryService
from ..services.scan_worker import (
    backfill_image_quality as _backfill_image_quality,
)
from ..services.scan_worker import (
    run_scan as _run_scan,
)
from ..services.scan_worker import (
    scan_lock,
)
from ..services.scan_worker import (
    scan_summary_message as _scan_summary_message,
)
from ..services.settings_service import (
    decrypt_user_settings as _decrypt_user_settings,
)
from ..services.settings_service import (
    is_public_site as _is_public_site,
)
from ..services.settings_service import (
    settings_public as _settings_public,
)
from ..services.settings_service import (
    update_runtime_settings as _update_runtime_settings,
)
from ..services.tag_sync import TagSyncService
from ..services.tag_sync_worker import (
    _TRANSLATION_RELEASE_API,
)
from ..services.tag_sync_worker import (
    category_refresh_once as _category_refresh_once,
)
from ..services.tag_sync_worker import (
    claim_jobs as _claim_jobs,
)
from ..services.tag_sync_worker import (
    complete_job as _complete_job,
)
from ..services.tag_sync_worker import (
    enqueue_job as _enqueue_job,
)
from ..services.tag_sync_worker import (
    enqueue_tag_sync as _enqueue_tag_sync,
)
from ..services.tag_sync_worker import (
    fetch_translation_db as _fetch_translation_db,
)
from ..services.tag_sync_worker import (
    jobs_count as _jobs_count,
)
from ..services.tag_sync_worker import (
    requeue_job as _requeue_job,
)
from ..services.tag_sync_worker import (
    tag_facets_cached as _tag_facets_cached,
)
from ..services.tag_sync_worker import (
    tag_sync_worker_loop as _tag_sync_worker_loop,
)
from ..services.tag_sync_worker import (
    translation_download_url as _translation_download_url,
)
from ..services.tag_sync_worker import (
    translation_update_loop as _translation_update_loop,
)
from ..services.tag_sync_worker import (
    translation_update_once as _translation_update_once,
)
from ..services.tag_translation import load_translations
from ..services.tasks import default_task_manager
from ..services.telegram import TelegramNotifier
from ..services.telegram_bot import TelegramBotService
from ..services.thumbnail_worker import (
    seed_thumbnails as _seed_thumbnails,
)
from ..services.thumbnail_worker import (
    thumbnail_gallery as _thumbnail_gallery,
)
from ..services.thumbnail_worker import (
    thumbnail_worker_loop as _thumbnail_worker_loop,
)
from ..services.thumbnails import ThumbnailService
from ..services.updates_worker import (
    detect_gallery_updates as _detect_gallery_updates,
)
from ..services.updates_worker import (
    finalize_gallery_update as _finalize_gallery_update,
)
from ..services.updates_worker import (
    gallery_updates_finalize_loop as _gallery_updates_finalize_loop,
)
from ..services.updates_worker import (
    normalize_update_title as _normalize_update_title,
)
from ..services.updates_worker import (
    record_gallery_update_log as _record_gallery_update_log,
)
from ..services.updates_worker import (
    run_gallery_updates as _run_gallery_updates,
)
from .dependencies import (
    db_error as _db_error,
)
from .dependencies import (
    display_title,
    resolve_display_title,
)
from .dependencies import (
    image_content_type as _image_content_type,
)
from .dependencies import (
    spawn_task as _spawn,
)
from .routers import (
    auth,
    core,
    downloads,
    duplicates,
    favorites,
    galleries,
    tags,
    tasks,
    updates,
)
from .routers import (
    settings as settings_router,
)
from .schemas import (
    ArchivePreviewRequest,
    BulkDeleteRequest,
    DownloadOriginalRequest,
    DownloadRequest,
    DownloadSelectedRequest,
    DuplicateIgnoreRequest,
    FavoriteCategoryRequest,
    FavoritesRemoveRequest,
    FilteredDeleteRequest,
    ProgressRequest,
    SettingsRequest,
    UpdateIdsRequest,
)
from .state import app_state

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)
logger = logging.getLogger(__name__)

CSRF_COOKIE = "galleryvault_csrf"

__all__ = [
    "CSRF_COOKIE",
    "DEFAULT_PASSWORD",
    "FAVORITES_SKIP_LIMIT",
    "LOGIN_RATE_MAX",
    "LOGIN_RATE_WINDOW",
    "_TRANSLATION_RELEASE_API",
    "AppConfig",
    "ArchivePreviewRequest",
    "BackgroundJobsRepository",
    "BulkDeleteRequest",
    "DownloadOriginalRequest",
    "DownloadRepository",
    "DownloadRequest",
    "DownloadSelectedRequest",
    "DownloadTask",
    "DownloadTaskModel",
    "Downloader",
    "DuplicateIgnoreRequest",
    "EhClient",
    "FavoriteCategoryRequest",
    "FavoriteItem",
    "FavoritesMonitor",
    "FavoritesRemoveRequest",
    "FavoritesRepository",
    "FavoritesService",
    "FilteredDeleteRequest",
    "Gallery",
    "GalleryIngestService",
    "GalleryMeta",
    "GalleryPage",
    "GalleryRepository",
    "GalleryTag",
    "GalleryUpdatesRepository",
    "LibraryService",
    "PageInfo",
    "ProgressRequest",
    "SettingsRepository",
    "SettingsRequest",
    "Tag",
    "TagSyncService",
    "TelegramBotService",
    "TelegramNotifier",
    "ThumbnailService",
    "UpdateIdsRequest",
    "_FavoriteDownloadQueue",
    "_FavoritesRepositoryProxy",
    "_apply_persisted_settings",
    "_auth_hash_configured",
    "_auth_runtime_hash",
    "_backfill_image_quality",
    "_bootstrap_auth",
    "_cancelled",
    "_category_refresh_once",
    "_claim_jobs",
    "_clear_cancelled",
    "_client_ip",
    "_closing_stream",
    "_complete_job",
    "_db_error",
    "_decrypt_user_settings",
    "_delete_local_copy",
    "_detect_gallery_updates",
    "_download_cancelled",
    "_download_progress",
    "_download_retry_sweep_loop",
    "_download_worker_loop",
    "_enqueue_job",
    "_enqueue_tag_sync",
    "_ensure_translation_updater",
    "_estimate_cloud_size",
    "_fav_counts_cache",
    "_favorite_counts_cached",
    "_favorite_size_sync",
    "_favorites_metadata",
    "_favorites_poll_loop",
    "_favorites_skip_decision",
    "_fetch_translation_db",
    "_finalize_gallery_update",
    "_gallery",
    "_gallery_tags",
    "_gallery_updates_finalize_loop",
    "_image_content_type",
    "_img_data_uri",
    "_in_scan_roots",
    "_infer_image_quality",
    "_ingest_downloaded_gallery",
    "_is_public_site",
    "_is_trusted_proxy",
    "_jobs_count",
    "_login_attempts",
    "_login_gate",
    "_login_lock",
    "_login_succeeded",
    "_maybe_scan_after_download",
    "_meta",
    "_migrate_plaintext_secrets",
    "_must_change_password",
    "_normalize_update_title",
    "_page_media_type",
    "_parse_gdata_tags",
    "_password_effective",
    "_persist_task_history",
    "_prune_merged_stale_pages",
    "_record_download_notification",
    "_record_gallery_update_log",
    "_record_task",
    "_refresh_favorite_counts",
    "_refresh_services",
    "_remote_cover_cache_dir",
    "_remote_cover_data_batch",
    "_remove_superseded_copy",
    "_request_cancel",
    "_requeue_job",
    "_restore_task_history",
    "_retry_backoff",
    "_run_download",
    "_run_duplicates_scan",
    "_run_favorites_check",
    "_run_gallery_updates",
    "_run_scan",
    "_runtime_row",
    "_scan_roots",
    "_scan_summary_message",
    "_seed_thumbnails",
    "_settings",
    "_settings_public",
    "_settings_session",
    "_spawn",
    "_start_telegram_bot",
    "_tag_facets_cached",
    "_tag_sync_worker_loop",
    "_tags_to_gdata_strings",
    "_telegram_flush_loop",
    "_thumb_service",
    "_thumbnail_gallery",
    "_thumbnail_worker_loop",
    "_translation_download_url",
    "_translation_update_loop",
    "_translation_update_once",
    "_unix_to_iso",
    "_update_runtime_settings",
    "app",
    "decrypt_json_or_value",
    "decrypt_or_plain",
    "delete_galleries_local",
    "display_title",
    "duplicates_state",
    "encrypt",
    "encrypt_json",
    "encryption_enabled",
    "favorites_check_state",
    "gallery_updates_state",
    "is_encrypted",
    "lifespan",
    "load_translations",
    "logger",
    "messages",
    "metadata_sync_state",
    "parse_gallery_url",
    "registry",
    "resolve_display_title",
    "scan_lock",
    "scan_state",
    "settings",
    "shutdown",
    "startup",
    "tag_sync_state",
    "task_history",
    "thumb_state",
    "translation_state",
    "verify_login_password",
]

# Wire state container
app_state.settings = settings
app_state.task_manager = default_task_manager
app_state.engine, app_state.session_factory = create_database(settings)
default_task_manager.session_factory = app_state.session_factory

# Aliases pointing directly to task manager state dictionaries for backward compatibility
scan_state = default_task_manager.scan_state
tag_sync_state = default_task_manager.tag_sync_state
thumb_state = default_task_manager.thumb_state
favorites_check_state = default_task_manager.favorites_check_state
duplicates_state = default_task_manager.duplicates_state
gallery_updates_state = default_task_manager.gallery_updates_state
metadata_sync_state = default_task_manager.metadata_sync_state
translation_state = default_task_manager.translation_state
task_history = default_task_manager.task_history
_download_cancelled = default_task_manager._cancelled_tasks

# Background task handles
download_worker_task: asyncio.Task | None = None
download_retry_sweep_task: asyncio.Task | None = None
gallery_updates_finalize_task: asyncio.Task | None = None
telegram_flush_task: asyncio.Task | None = None
tag_sync_worker_task: asyncio.Task | None = None
translation_update_task: asyncio.Task | None = None
thumb_worker_task: asyncio.Task | None = None


def _settings() -> Settings:
    # app_state is the canonical source; adopt monkeypatched app.state.settings
    # so tests that set app.state.settings continue to work.
    patched = None
    if "app" in globals() and hasattr(app, "state"):
        patched = getattr(app.state, "settings", None)
        if patched is not None and patched is not app_state.settings:
            app_state.settings = patched
            return patched
    if app_state.settings is not None:
        return app_state.settings
    if patched is not None:
        return patched
    return get_settings()


def _sync_state() -> None:
    """Mirror app_state <-> app.state so monkeypatched tests stay consistent.

    app_state is canonical; app.state is a legacy alias that tests mutate
    directly. After any service is (re)created we ensure both point to the same
    objects. If a test patched app.state with a different object, adopt it.
    """
    for attr in (
        "settings",
        "engine",
        "session_factory",
        "eh_client",
        "downloader",
        "telegram",
        "favorites_service",
        "library_service",
        "tag_service",
        "thumbnail_service",
        "spawned_tasks",
    ):
        patched = getattr(app.state, attr, None) if "app" in globals() and hasattr(app, "state") and hasattr(app.state, attr) else None
        canonical = getattr(app_state, attr, None)
        # Adopt monkeypatched value into canonical store (tests patch app.state directly).
        if patched is not None and patched is not canonical:
            setattr(app_state, attr, patched)
            if attr == "spawned_tasks" and isinstance(patched, set):
                app_state.extra["spawned_tasks"] = patched
        # Ensure app.state mirrors canonical.
        can = getattr(app_state, attr, None)
        if can is not None:
            try:
                setattr(app.state, attr, can)
            except Exception:  # noqa: BLE001, S110
                pass
        elif patched is not None:
            try:
                setattr(app_state, attr, patched)
            except Exception:  # noqa: BLE001, S110
                pass
    # Keep extra["spawned_tasks"] in sync
    if "app" in globals() and hasattr(app, "state"):
        try:
            app_state.extra["spawned_tasks"] = getattr(app.state, "spawned_tasks", set())
        except Exception:  # noqa: BLE001, S110
            pass


def _create_services(settings_obj: Settings) -> dict[str, object]:
    """Factory used by startup and _refresh_services (replaces globals().get trick).

    Respects test monkeypatches: if globals() contains a replacement class (e.g.
    tests patch EhClient), that class is used instead of the real one.
    """
    eh_cls = globals().get("EhClient", EhClient)
    dl_cls = globals().get("Downloader", Downloader)
    tg_cls = globals().get("TelegramNotifier", TelegramNotifier)
    fav_cls = globals().get("FavoritesService", FavoritesService)
    fav_proxy_cls = globals().get("_FavoritesRepositoryProxy", _FavoritesRepositoryProxy)
    fav_queue_cls = globals().get("_FavoriteDownloadQueue", _FavoriteDownloadQueue)
    client = eh_cls(settings_obj, max_concurrency=settings_obj.exhentai_max_concurrency)
    downloader = dl_cls(
        client,
        settings_obj.download_root,
        concurrency=settings_obj.download_concurrency,
        page_concurrency=settings_obj.page_concurrency,
    )
    telegram = tg_cls(settings_obj)
    favorites_service = fav_cls(client, fav_proxy_cls(), fav_queue_cls(), telegram)
    return {
        "eh_client": client,
        "downloader": downloader,
        "telegram": telegram,
        "favorites_service": favorites_service,
    }


def _settings_session() -> AsyncIterator[AsyncSession]:
    assert app_state.session_factory is not None
    return app_state.session_factory()


def _record_task(
    task: str,
    started_at: str | None,
    completed_at: str | None,
    status: str,
    reason: str = "",
    done: int = 0,
    total: int = 0,
) -> None:
    default_task_manager.record_task(task, started_at, completed_at, status, reason, done, total)
    _spawn(default_task_manager.persist_history(), "persist task history")


async def _persist_task_history() -> None:
    await default_task_manager.persist_history()


async def _restore_task_history() -> None:
    await default_task_manager.restore_history()


def _request_cancel(task_key: str | int) -> None:
    default_task_manager.request_cancel(task_key)


def _clear_cancelled(task_key: str | int) -> None:
    default_task_manager.clear_cancelled(task_key)


def _cancelled(task_key: str | int) -> bool:
    return default_task_manager.is_cancelled(task_key)


def _password_effective() -> str | None:
    s = _settings()
    if s.auth_password_hash:
        return s.auth_password_hash
    if s.auth_password:
        return s.auth_password
    return None


def _must_change_password() -> bool:
    s = _settings()
    auth_hash_configured = bool(s.auth_password_hash or s.auth_password)
    return bool(s.auth_required and (not auth_hash_configured or s.auth_password == DEFAULT_PASSWORD))


def _auth_hash_configured() -> bool:
    return bool(_settings().auth_password_hash or _settings().auth_password)


def _scan_roots() -> list[str]:
    roots = list(_settings().library_roots)
    if _settings().download_root not in roots:
        roots.append(_settings().download_root)
    return normalize_library_roots(roots)


def _thumb_service() -> ThumbnailService:
    if app_state.thumbnail_service is not None:
        return app_state.thumbnail_service
    s = _settings()
    service = ThumbnailService(s.thumbnail_cache_dir)
    app_state.thumbnail_service = service
    return service


def _remote_cover_cache_dir() -> Path:
    d = Path(_settings().thumbnail_cache_dir).parent / "remote-covers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _img_data_uri(raw: bytes) -> str | None:
    from ..services.favorites_worker import _img_data_uri as f_img
    return f_img(raw)


def _unix_to_iso(val: Any) -> str | None:
    from ..services.favorites_worker import _unix_to_iso as f_iso
    return f_iso(val)


def _parse_gdata_tags(tags: list[str]) -> list[tuple[str, str]]:
    from ..services.favorites_worker import _parse_gdata_tags as f_tags
    return f_tags(tags)


def _tags_to_gdata_strings(raw_tags: list[object]) -> list[str]:
    out: list[str] = []
    for tag in raw_tags or []:
        if isinstance(tag, dict):
            ns = str(tag.get("namespace") or "")
            name = str(tag.get("name") or "")
        elif isinstance(tag, (list, tuple)) and len(tag) >= 2:
            ns, name = str(tag[0] or ""), str(tag[1] or "")
        else:
            continue
        name = name.strip()
        if not name:
            continue
        out.append(f"{ns}:{name}" if ns else name)
    return out


def _page_media_type(ext: str) -> str:
    return {"jpg": "image/jpeg", "jpe": "image/jpeg", "jpeg": "image/jpeg"}.get(
        (ext or "").lower(), f"image/{ext}"
    )


def _closing_stream(stream: Any) -> Any:
    from .routers.galleries import _closing_stream as g_closing
    return g_closing(stream)


def _meta(row: Gallery, pages: list[GalleryPage]) -> GalleryMeta:
    from .routers.galleries import _meta as g_meta
    return g_meta(row, pages)


async def _gallery(identifier: int) -> tuple[Gallery, list[GalleryPage]]:
    from .routers.galleries import _gallery_lookup
    return await _gallery_lookup(identifier)


async def _gallery_tags(gallery_id: int) -> list[tuple[str, str]]:
    from .routers.galleries import _gallery_tags_lookup
    return await _gallery_tags_lookup(gallery_id)


async def _runtime_row() -> dict[str, Any]:
    async with _settings_session() as session:
        row = await session.get(AppConfig, "runtime_auth")
        return dict(row.value) if row else {}


async def _apply_persisted_settings() -> None:
    try:
        async with _settings_session() as session:
            persisted = await SettingsRepository(session).get()
        persisted = _decrypt_user_settings(persisted)
        runtime = await _runtime_row()
        updates_dict: dict[str, object] = {**persisted}
        _update_runtime_settings(updates_dict)
        if runtime.get("auth_password_hash"):
            updated = app_state.settings.model_copy(
                update={"auth_password_hash": decrypt_or_plain(runtime["auth_password_hash"])}
            )
            app_state.settings = updated
            try:
                app.state.settings = updated
            except Exception:  # noqa: BLE001, S110
                pass
        else:
            _sync_state()
    except Exception as exc:  # noqa: BLE001
        logger.warning("user settings could not be loaded", extra={"error": str(exc)})


async def _bootstrap_auth() -> None:
    runtime = await _runtime_row()
    updates_dict: dict[str, object] = {}
    if not runtime.get("auth_secret"):
        if _settings().auth_secret:
            updates_dict["auth_secret"] = _settings().auth_secret
        else:
            import secrets as _secrets
            updates_dict["auth_secret"] = _secrets.token_urlsafe(32)
    if _settings().auth_password_hash and not runtime.get("auth_password_hash"):
        updates_dict["auth_password_hash"] = _settings().auth_password_hash
    if updates_dict:
        merged = {**runtime, **updates_dict}
        if encryption_enabled():
            for _key in ("auth_secret", "auth_password_hash"):
                if isinstance(merged.get(_key), str):
                    merged[_key] = encrypt(merged[_key])
        async with _settings_session() as session, session.begin():
            row = await session.get(AppConfig, "runtime_auth")
            if row is None:
                session.add(AppConfig(key="runtime_auth", value=merged))
            else:
                row.value = merged
    final = await _runtime_row()
    opts: dict[str, object] = {"auth_secret": decrypt_or_plain(final.get("auth_secret"))}
    if final.get("auth_password_hash"):
        opts["auth_password_hash"] = decrypt_or_plain(final["auth_password_hash"])
    updated = app_state.settings.model_copy(update=opts)
    app_state.settings = updated
    try:
        app.state.settings = updated
    except Exception:  # noqa: BLE001, S110
        pass
    _sync_state()


async def _auth_runtime_hash() -> str | None:
    runtime = await _runtime_row()
    value = runtime.get("auth_password_hash")
    return decrypt_or_plain(value) if value else None


async def _migrate_plaintext_secrets() -> None:
    if not encryption_enabled():
        return
    try:
        async with _settings_session() as session, session.begin():
            runtime_row = await session.get(AppConfig, "runtime_auth")
            if runtime_row is not None and isinstance(runtime_row.value, dict):
                value = dict(runtime_row.value)
                changed = False
                for _key in ("auth_secret", "auth_password_hash"):
                    v = value.get(_key)
                    if isinstance(v, str) and v and not is_encrypted(v):
                        value[_key] = encrypt(v)
                        changed = True
                if changed:
                    runtime_row.value = value
            user = await SettingsRepository(session).get()
            changed = False
            cookies = user.get("exhentai_cookies")
            if isinstance(cookies, (dict, list)) and cookies:
                user["exhentai_cookies"] = encrypt_json(cookies)
                changed = True
            token = user.get("telegram_bot_token")
            if isinstance(token, str) and token and not is_encrypted(token):
                user["telegram_bot_token"] = encrypt(token)
                changed = True
            if changed:
                await SettingsRepository(session).save(user)
        if encryption_enabled():
            logger.info("at-rest secret encryption enabled; plaintext values migrated")
    except Exception as exc:  # noqa: BLE001
        logger.warning("plaintext secret migration failed", extra={"error": str(exc)})


def _ensure_translation_updater() -> asyncio.Task | None:
    global translation_update_task
    if (
        translation_update_task is None or translation_update_task.done()
    ) and _settings().tag_translation_update_interval_minutes > 0:
        task = _spawn(_translation_update_loop(), "translation updater")
        if task is not None:
            translation_update_task = task
        else:
            # Fallback if no running loop (e.g. called synchronously outside event loop)
            translation_update_task = asyncio.create_task(_translation_update_loop())
    return translation_update_task


async def _refresh_services() -> None:
    _sync_state()
    old_client = getattr(app_state, "eh_client", None) or getattr(app.state, "eh_client", None)
    old_telegram = getattr(app_state, "telegram", None) or getattr(app.state, "telegram", None)
    if old_telegram is not None:
        if hasattr(old_telegram, "flush_summary"):
            await old_telegram.flush_summary()
        if hasattr(old_telegram, "aclose"):
            await old_telegram.aclose()
    if old_client is not None and hasattr(old_client, "aclose"):
        await old_client.aclose()

    settings_obj = _settings()
    services = _create_services(settings_obj)
    for key, obj in services.items():
        setattr(app_state, key, obj)
        try:
            setattr(app.state, key, obj)
        except Exception:  # noqa: BLE001, S110
            pass

    _start_telegram_bot()
    # Keep library/tag/thumbnail services in sync (previously missed, leading to stale app.state)
    _sync_state()
    _ensure_translation_updater()


def _start_telegram_bot() -> None:
    _sync_state()
    if getattr(app.state, "telegram_bot_task", None) is not None and hasattr(app.state.telegram_bot_task, "cancel"):
        try:
            app.state.telegram_bot_task.cancel()
        except Exception:  # noqa: BLE001, S110
            pass
        app_state.extra.get("spawned_tasks", set()).discard(app.state.telegram_bot_task)
    bot_cls = globals().get("TelegramBotService", TelegramBotService)
    fav_queue_cls = globals().get("_FavoriteDownloadQueue", _FavoriteDownloadQueue)
    if _settings().telegram_bot_token and getattr(app_state, "telegram", None) is not None:
        task = _spawn(
            bot_cls(
                _settings(),
                client=getattr(app_state.telegram, "client", None),
                queue=fav_queue_cls(),
                notifier=app_state.telegram,
            ).run(),
            "telegram bot",
        )
        # Fallback if no running loop (e.g. called outside event loop in tests)
        if task is None:
            try:
                task = asyncio.create_task(
                    bot_cls(
                        _settings(),
                        client=getattr(app_state.telegram, "client", None),
                        queue=fav_queue_cls(),
                        notifier=app_state.telegram,
                    ).run()
                )
            except RuntimeError:
                task = None
        if task is not None:
            app.state.telegram_bot_task = task
            # Also keep in app_state for shutdown discovery
            app_state.extra.setdefault("spawned_tasks", set()).add(task)


async def startup() -> None:
    global download_worker_task, download_retry_sweep_task, gallery_updates_finalize_task
    global telegram_flush_task, tag_sync_worker_task, thumb_worker_task

    # Canonical source is app_state; keep app.state in sync for legacy monkeypatch compat
    _sync_state()
    if not hasattr(app.state, "spawned_tasks") or not isinstance(getattr(app.state, "spawned_tasks", None), set):
        app.state.spawned_tasks = set()
    app_state.extra["spawned_tasks"] = app.state.spawned_tasks
    # Ensure app_state mirrors app.state for spawned_tasks
    _sync_state()

    try:
        async with _settings_session() as session:
            repo_cls = globals().get("SettingsRepository", SettingsRepository)
            persisted = await repo_cls(session).get()
        _update_runtime_settings(_decrypt_user_settings(persisted))
        _sync_state()
    except Exception:  # noqa: BLE001
        logger.warning("user settings could not be loaded at startup")

    try:
        await globals().get("_bootstrap_auth", _bootstrap_auth)()
        await globals().get("_migrate_plaintext_secrets", _migrate_plaintext_secrets)()
        await globals().get("_restore_task_history", _restore_task_history)()
    except Exception:  # noqa: BLE001
        logger.warning("auth bootstrap failed; using temporary credentials")

    settings_obj = _settings()
    services = _create_services(settings_obj)
    for key, obj in services.items():
        setattr(app_state, key, obj)
        try:
            setattr(app.state, key, obj)
        except Exception:  # noqa: BLE001, S110
            pass
    globals().get("_start_telegram_bot", _start_telegram_bot)()
    _sync_state()
    # favorite_poll_task should be tracked via spawned_tasks, but keep legacy attr for tests
    poll_coro = globals().get("_favorites_poll_loop", _favorites_poll_loop)()
    poll_task = _spawn(poll_coro, "favorites poll")
    if poll_task is None:
        try:
            poll_task = asyncio.create_task(poll_coro)
        except RuntimeError:
            poll_task = None
        else:
            # If _spawn failed due to no loop, we still need to close coro
            if poll_task is None and hasattr(poll_coro, "close"):
                poll_coro.close()
    if poll_task is not None:
        app.state.favorite_poll_task = poll_task

    globals().get("_spawn", _spawn)(
        globals().get("_refresh_favorite_counts", _refresh_favorite_counts)(),
        "favorite counts startup warmup",
    )

    # Clean partial downloads
    try:
        import shutil as _shutil

        keep_gids: set[int] = set()
        try:
            async with _settings_session() as session:
                rows = await session.execute(
                    select(DownloadTaskModel.gid).where(
                        DownloadTaskModel.status.in_(["pending", "downloading"])
                    )
                )
                keep_gids = {int(row[0]) for row in rows}
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not read active downloads for temp sweep", extra=log_extra(error=type(exc).__name__))
        _root = Path(_settings().download_root)
        for _child in _root.glob(".gv-*"):
            gid_text = _child.name[len(".gv-"):] if _child.name.startswith(".gv-") else ""
            if gid_text.isdigit() and int(gid_text) in keep_gids:
                continue
            if _child.is_dir():
                _shutil.rmtree(_child, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("partial download cleanup failed", extra=log_extra(error=type(exc).__name__))

    download_worker_task = asyncio.create_task(
        globals().get("_download_worker_loop", _download_worker_loop)()
    )
    download_retry_sweep_task = asyncio.create_task(
        globals().get("_download_retry_sweep_loop", _download_retry_sweep_loop)()
    )
    gallery_updates_finalize_task = asyncio.create_task(
        globals().get("_gallery_updates_finalize_loop", _gallery_updates_finalize_loop)()
    )
    telegram_flush_task = asyncio.create_task(
        globals().get("_telegram_flush_loop", _telegram_flush_loop)()
    )
    tag_sync_worker_task = asyncio.create_task(
        globals().get("_tag_sync_worker_loop", _tag_sync_worker_loop)()
    )
    thumb_worker_task = asyncio.create_task(
        globals().get("_thumbnail_worker_loop", _thumbnail_worker_loop)()
    )

    if not encryption_enabled():
        logger.warning(
            "ENCRYPTION_KEY not set; exhentai_cookies and auth secrets will be stored in plaintext. "
            "Set ENCRYPTION_KEY to enable at-rest encryption and avoid plaintext persistence."
        )
    if _settings().generate_thumbnails:
        try:
            await globals().get("_seed_thumbnails", _seed_thumbnails)()
        except Exception as exc:  # noqa: BLE001
            logger.warning("thumbnail seeding failed", extra=log_extra(error=type(exc).__name__))
    globals().get("_ensure_translation_updater", _ensure_translation_updater)()
    # Do not block lifespan on translation DB load; /healthz should be ready ASAP.
    try:
        coro = asyncio.to_thread(load_translations)
        t = _spawn(coro, "load translations")
        if t is None:
            # No running loop (e.g. sync test harness) — run inline
            await coro
    except RuntimeError:
        # Fallback: no loop, run synchronously
        try:
            await asyncio.to_thread(load_translations)
        except Exception:  # noqa: BLE001, S110
            pass
    logger.info("GalleryVault started", extra=log_extra(library_roots=_settings().library_roots))
    _sync_state()
    # Guard: canonical and legacy state must stay in sync
    try:
        assert app_state.settings is app.state.settings
    except AssertionError:
        logger.warning("state mirror diverged after startup", extra=log_extra(canonical=id(app_state.settings), legacy=id(app.state.settings)))


async def shutdown() -> None:
    # Collect all tracked background tasks from both mirrors
    all_spawned: set[asyncio.Task] = set()
    for src in (getattr(app.state, "spawned_tasks", None), app_state.extra.get("spawned_tasks")):
        if isinstance(src, set):
            all_spawned.update(src)
    for task in list(all_spawned):
        task.cancel()
    for task in list(all_spawned):
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    if translation_update_task is not None:
        translation_update_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await translation_update_task
    poll_task = getattr(app.state, "favorite_poll_task", None)
    if poll_task is not None:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task
    bot_task = getattr(app.state, "telegram_bot_task", None)
    if bot_task is not None:
        bot_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bot_task
    if download_worker_task is not None:
        download_worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await download_worker_task
    if tag_sync_worker_task is not None:
        tag_sync_worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await tag_sync_worker_task
    if thumb_worker_task is not None:
        thumb_worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await thumb_worker_task
    if telegram_flush_task is not None:
        telegram_flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await telegram_flush_task
    if getattr(app.state, "telegram", None) is not None:
        await app.state.telegram.flush_summary()
        await app.state.telegram.aclose()
    if getattr(app.state, "eh_client", None) is not None:
        await app.state.eh_client.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup()
    try:
        yield
    finally:
        await shutdown()


app = FastAPI(title="GalleryVault", lifespan=lifespan)
app.state.settings = settings
app.state.engine = app_state.engine
app.state.session_factory = app_state.session_factory
app.state.downloader = None
app.state.favorites_service = None
app.state.eh_client = None
app.state.telegram = None
app.state.favorite_poll_task = None
app.state.telegram_bot_task = None
app.state.spawned_tasks = set()


@app.middleware("http")
async def authentication(request: Request, call_next):
    path = request.url.path
    if path in {"/healthz", "/metrics", "/login", "/logout"}:
        response = await call_next(request)
        # Ensure CSRF cookie is set for subsequent POSTs when auth is required
        if _settings().auth_required and not request.cookies.get(CSRF_COOKIE):
            try:
                token = secrets.token_urlsafe(32)
                # Use lax, not httponly so JS can read it for X-CSRF-Token header
                secure = _settings().auth_cookie_secure or request.headers.get("x-forwarded-proto", "").lower() == "https" or request.url.scheme == "https"
                response.set_cookie(CSRF_COOKIE, token, samesite="lax", secure=secure, httponly=False, max_age=86400 * 30)
            except Exception:  # noqa: BLE001, S110
                pass
        return response
    if not _settings().auth_required:
        return await call_next(request)
    if not verify_session(
        request.cookies.get(_settings().auth_cookie_name), _settings().auth_secret or ""
    ):
        reason = "missing_or_invalid_session"
        logger.info(
            "authentication failed",
            extra=log_extra(ip=request.client.host if request.client else "unknown", reason=reason),
        )
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Authentication required"},
                status_code=401,
            )
        return RedirectResponse("/login", status_code=303)

    # CSRF / Origin protection for state-changing requests
    if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
        # API routes: Origin / Referer / Sec-Fetch-Site + optional X-CSRF-Token
        if request.url.path.startswith("/api/"):
            sec_fetch_site = request.headers.get("sec-fetch-site")
            if sec_fetch_site == "cross-site":
                return JSONResponse(
                    {"detail": "Cross-origin request rejected"},
                    status_code=403,
                )
            # Prefer X-Forwarded-Host if behind trusted proxy, else Host
            host_header = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
            # Compare hostname only, ignoring port: nginx $host strips the port
            # (e.g. Host=192.168.1.123 vs Origin=http://192.168.1.123:8000). Using
            # netloc would false-positive on every non-80 port. hostname still
            # blocks genuine cross-site (evil.com vs gallery host).
            parsed_host = urlparse("//" + host_header)
            request_host = (parsed_host.hostname or "").lower()
            # Origin check (primary)
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")
            csrf_cookie = request.cookies.get(CSRF_COOKIE)
            csrf_header = request.headers.get("x-csrf-token")
            if origin:
                parsed_origin = urlparse(origin)
                origin_host = (parsed_origin.hostname or "").lower()
                if origin_host and request_host and origin_host != request_host:
                    return JSONResponse(
                        {"detail": "Cross-origin request rejected"},
                        status_code=403,
                    )
            elif referer:
                parsed_referer = urlparse(referer)
                referer_host = (parsed_referer.hostname or "").lower()
                if referer_host and request_host and referer_host != request_host:
                    return JSONResponse(
                        {"detail": "Cross-origin request rejected"},
                        status_code=403,
                    )
            else:
                # No Origin/Referer: fall back to CSRF token validation if both present
                # Old browsers or curl without Origin would otherwise bypass.
                if csrf_cookie and csrf_header and not hmac.compare_digest(csrf_cookie, csrf_header):
                    return JSONResponse({"detail": "CSRF token required"}, status_code=403)
                # If no CSRF cookie yet, allow (will be set on response below) — same-origin fetch without Origin is normal
        # Non-API POST (form) — strict CSRF
        elif request.url.path not in {"/login", "/logout"}:
            csrf = request.cookies.get(CSRF_COOKIE)
            supplied = request.headers.get("x-csrf-token")
            content_type = request.headers.get("content-type", "").split(";", 1)[0]
            if content_type == "application/x-www-form-urlencoded":
                body = await request.body()
                supplied = parse_qs(body.decode(errors="replace")).get("csrf_token", [None])[0]

                async def receive():
                    return {"type": "http.request", "body": body, "more_body": False}

                request._receive = receive
            if not csrf or not supplied or not hmac.compare_digest(csrf, supplied):
                return HTMLResponse("CSRF token required", status_code=403)
    response = await call_next(request)
    # Ensure CSRF cookie is present for future requests (30-day, lax)
    if not request.cookies.get(CSRF_COOKIE) and _settings().auth_required:
        try:
            token = secrets.token_urlsafe(32)
            secure = _settings().auth_cookie_secure or request.headers.get("x-forwarded-proto", "").lower() == "https" or request.url.scheme == "https"
            response.set_cookie(CSRF_COOKIE, token, samesite="lax", secure=secure, httponly=False, max_age=86400 * 30)
        except Exception:  # noqa: BLE001, S110
            pass
    return response


@app.middleware("http")
async def request_id(request: Request, call_next):
    return await request_id_middleware(request, call_next)


# Include all routers
app.include_router(core.router)
app.include_router(auth.router)
app.include_router(galleries.router)
app.include_router(downloads.router)
app.include_router(settings_router.router)
app.include_router(favorites.router)
app.include_router(tags.router)
app.include_router(tasks.router)
app.include_router(duplicates.router)
app.include_router(updates.router)
