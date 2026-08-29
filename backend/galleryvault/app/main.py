import asyncio
import base64
import contextlib
import hmac
import logging
import re
import time as _time
from collections import deque
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from ..auth import create_session, hash_password, verify_password, verify_session
from ..config import (
    Settings,
    get_settings,
    library_root_warnings,
    normalize_library_roots,
)
from ..db.models import DownloadTask as DownloadTaskModel
from ..db.models import Gallery, GalleryPage, GalleryTag, Tag
from ..db.repository import (
    BackgroundJobsRepository,
    DownloadRepository,
    FavoritesRepository,
    GalleryRepository,
    SettingsRepository,
)
from ..db.session import create_database
from ..logging import configure_logging, log_extra
from ..observability import request_id_middleware
from ..scanners import registry
from ..scanners.base import GalleryMeta, PageInfo
from ..scanners.ehviewer import IMAGE_EXTENSIONS, natural_key
from ..secrets import (
    decrypt_json_or_value,
    decrypt_or_plain,
    encrypt,
    encrypt_json,
    encryption_enabled,
    is_encrypted,
)
from ..services import messages
from ..services.downloader import DownloadCancelledError, Downloader, DownloadTask
from ..services.duplicates import find_duplicate_groups
from ..services.eh_client import EhClient, EhClientError, GalleryGoneError, parse_gallery_url
from ..services.favorites import FavoritesService
from ..services.ingest import GalleryIngestService
from ..services.library import LibraryService
from ..services.tag_sync import (
    TagSyncService,
)
from ..services.tag_translation import (
    load_translations,
    merge_translation_data,
    translated_tag,
)
from ..services.telegram import TelegramNotifier
from ..services.telegram_bot import TelegramBotService
from ..services.thumbnails import ThumbnailError, ThumbnailService

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)
logger = logging.getLogger(__name__)


app = FastAPI(title="GalleryVault")
app.state.settings = settings
app.state.engine, app.state.session_factory = create_database(settings)
app.state.downloader = None
app.state.favorites_service = None
app.state.eh_client = None
app.state.telegram = None
app.state.favorite_poll_task = None
app.state.telegram_bot_task = None
scan_state: dict[str, object] = {
    "running": False,
    "last": None,
    "started_at": None,
    "completed_at": None,
}
scan_lock = asyncio.Lock()
download_worker_task = None
download_retry_sweep_task = None
tag_sync_state: dict[str, object] = {
    "running": False,
    "total": 0,
    "queued": 0,
    "processed": 0,
    "succeeded": 0,
    "failed": 0,
    "retries": 0,
    "interval": None,
    "last_error": None,
    "started_at": None,
    "completed_at": None,
    "history_recorded": False,
    "category_refreshed": 0,
    "category_refresh_running": False,
}
tag_sync_holds: dict[int, int] = {}
tag_sync_worker_task = None
translation_update_task = None
telegram_flush_task = None
_download_cancelled: set[int] = set()
favorites_check_state: dict[str, object] = {
    "running": False,
    "categories": {},
    "last_error": None,
    "started_at": None,
    "completed_at": None,
    "history_recorded": False,
}
duplicates_state: dict[str, object] = {
    "running": False,
    "stage": None,
    "done": 0,
    "total": 0,
    "last_error": None,
    "groups": [],
}
metadata_sync_state: dict[str, object] = {
    "running": False,
    "stage": None,
    "done": 0,
    "total": 0,
    "applied": 0,
    "last_error": None,
    "started_at": None,
    "completed_at": None,
}
_metadata_sync_active = 0
translation_state: dict[str, object] = {
    "running": False,
    "last": None,
    "last_error": None,
    "entries": 0,
    "started_at": None,
    "completed_at": None,
    "history_recorded": False,
}
CSRF_COOKIE = "galleryvault_csrf"
thumb_state: dict[str, object] = {
    "running": False,
    "queued": 0,
    "processed": 0,
    "succeeded": 0,
    "failed": 0,
    "total": 0,
    "last_error": None,
    "started_at": None,
    "completed_at": None,
    "history_recorded": False,
}
thumb_worker_task = None
thumb_service: ThumbnailService | None = None

# --- Background-task log ------------------------------------------------
# Latest-first record of finished/cancelled background tasks (scan, tag sync,
# thumbnail generation, favorite metadata sync).  Kept in memory like the rest
# of the task state; the Downloads page keeps its own persisted history.
task_history: deque[dict[str, object]] = deque(maxlen=200)
# Cancel requests, keyed by task name.  A worker checks this flag between units
# of work and stops at the next safe point.
_task_cancelled: set[str] = set()


def _record_task(
    task: str,
    started_at: str | None,
    completed_at: str | None,
    status: str,
    *,
    reason: str = "",
    done: int = 0,
    total: int = 0,
) -> None:
    """Append one finished/cancelled task to the activity log."""
    task_history.appendleft(
        {
            "task": task,
            "started_at": started_at or completed_at,
            "completed_at": completed_at,
            "status": status,
            "reason": reason,
            "done": done,
            "total": total,
        }
    )


def _request_cancel(task: str) -> None:
    _task_cancelled.add(task)


def _clear_cancelled(task: str) -> None:
    _task_cancelled.discard(task)


def _cancelled(task: str) -> bool:
    return task in _task_cancelled

# Built-in default password used when no auth hash is configured anywhere. The
# SPA forces a password change once you log in with it.  Documented in the
# frontend README.
DEFAULT_PASSWORD = "p1a2s3s4"

# Simple in-memory login rate limiter (per source IP) so a public instance is
# not trivially brute-forced.  A successful login clears the IP's history.
_login_attempts: dict[str, list[float]] = {}
_login_lock = asyncio.Lock()
LOGIN_RATE_WINDOW = 60.0
LOGIN_RATE_MAX = 10


async def _login_gate(ip: str) -> bool:
    """Return True if ``ip`` may attempt a login within the rate window."""
    import time as _time

    global _login_attempts
    now = _time.time()
    async with _login_lock:
        if len(_login_attempts) > 2048:
            cutoff = now - LOGIN_RATE_WINDOW
            _login_attempts = {
                key: [t for t in stamps if t >= cutoff]
                for key, stamps in _login_attempts.items()
                if any(t >= cutoff for t in stamps)
            }
        stamps = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_RATE_WINDOW]
        if len(stamps) >= LOGIN_RATE_MAX:
            return False
        _login_attempts[ip] = stamps + [now]
    return True


async def _login_succeeded(ip: str) -> None:
    async with _login_lock:
        _login_attempts.pop(ip, None)


def _settings() -> Settings:
    return app.state.settings


def _is_public_site(base_url: str) -> bool:
    """True when ``base_url`` points at the public E-Hentai mirror.

    Used to tell "gallery not found" apart from "this site cannot see a
    gallery that only ExHentai exposes": on e-hentai.org an ExHentai-only
    gallery returns the same 404/empty page as a deleted one, so the tag-sync
    worker must not reclassify it as deleted.
    """
    try:
        host = (urlsplit(base_url).hostname or "").lower()
    except ValueError:
        return False
    return host == "e-hentai.org" or host.endswith(".e-hentai.org")


def _password_effective() -> str | None:
    """Effective password for login: the configured hash, the legacy plaintext,
    or ``None`` when no password is configured (built-in default used)."""
    settings = _settings()
    return settings.auth_password_hash or settings.auth_password or None


def _must_change_password() -> bool:
    """The built-in default ``password`` is in effect AND login is required."""
    return _settings().auth_required and _password_effective() is None


def _auth_hash_configured() -> bool:
    return bool(_settings().auth_password_hash or _settings().auth_password)


_LEADING_NUMBER = re.compile(r"^\s*\d+[\s\-]+")


def resolve_display_title(title: str | None, title_jpn: str | None, directory: str = "") -> str:
    """Resolve a display title from raw title fields according to the configured
    ``title_display`` preference. Mirrors Ehviewer's ``getSuitableTitle`` and
    accepts ``title``/``title_jpn``/directory-name independently of any ORM
    object, so cloud-only favorite rows and duplicate-copy records can share the
    same logic as ``display_title``.
    """
    mode = (_settings().title_display or "japanese").lower()
    title = title or ""
    title_jpn = title_jpn or ""
    if mode == "english":
        source = title or title_jpn or directory
    elif mode == "directory":
        source = directory or title_jpn or title
    else:
        source = title_jpn or title or directory
    if not source:
        source = title or title_jpn or directory
    stripped = _LEADING_NUMBER.sub("", source).lstrip("-").strip()
    return stripped or source


def display_title(gallery: object) -> str:
    """Resolve the gallery title shown in the UI from the configured preference.

    Mirrors Ehviewer's ``getSuitableTitle``: Japanese by default, falling back
    to the romaji/English title, then to the directory name with any leading
    gallery id stripped.
    """
    storage_path = getattr(gallery, "storage_path", "") or ""
    directory = Path(storage_path).name if storage_path else ""
    resolved = resolve_display_title(
        getattr(gallery, "title", None),
        getattr(gallery, "title_jpn", None),
        directory,
    )
    return resolved or str(getattr(gallery, "gid", "") or "")


def _scan_roots() -> list[str]:
    roots = list(_settings().library_roots)
    if _settings().download_root not in roots:
        roots.append(_settings().download_root)
    return normalize_library_roots(roots)


@app.middleware("http")
async def authentication(request: Request, call_next):
    path = request.url.path
    if path in {"/healthz", "/metrics", "/login", "/logout"}:
        return await call_next(request)
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
            return HTMLResponse(
                '{"detail":"Authentication required"}',
                status_code=401,
                media_type="application/json",
            )
        return RedirectResponse("/login", status_code=303)
    # JSON APIs use the authenticated session and do not accept browser form
    # bodies; HTML forms use the double-submit token below.  Logging out is
    # exempt: it only clears the session and the SPA posts it without a form.
    if (
        request.method in {"POST", "PUT", "DELETE", "PATCH"}
        and request.url.path.startswith("/api/")
    ):
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlparse as _origin_parse

            origin_host = _origin_parse(origin).hostname
            request_hostname = _origin_parse("//" + request.headers.get("host", "")).hostname
            if origin_host and origin_host != request_hostname:
                return HTMLResponse(
                    '{"detail":"Cross-origin request rejected"}',
                    status_code=403,
                    media_type="application/json",
                )
    if (
        request.method == "POST"
        and request.url.path not in {"/login", "/logout"}
        and not request.url.path.startswith("/api/")
    ):
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
    return await call_next(request)


@app.middleware("http")
async def request_id(request: Request, call_next):
    # Registered after `authentication`, so it runs outermost (first): every
    # request gets an X-Request-ID header and its logs carry the same id.
    return await request_id_middleware(request, call_next)


async def _runtime_row() -> dict:
    """Read the DB row holding auth secrets (auth_secret, auth_password_hash)."""
    from ..db.models import AppConfig as _AppConfig

    async with _settings_session() as session:
        row = await session.get(_AppConfig, "runtime_auth")
        return dict(row.value) if row else {}


def _decrypt_user_settings(persisted: dict) -> dict:
    """Turn at-rest encrypted user settings back into plaintext values."""
    persisted = dict(persisted)
    cookies = persisted.get("exhentai_cookies")
    if is_encrypted(cookies):
        persisted["exhentai_cookies"] = decrypt_json_or_value(cookies)
    token = persisted.get("telegram_bot_token")
    if is_encrypted(token):
        persisted["telegram_bot_token"] = decrypt_or_plain(token)
    return persisted


async def _apply_persisted_settings() -> None:
    """Reload user settings + runtime secrets from the DB into app.state.

    The database is the single source of truth: user-editable settings live in
    ``app_config.user_settings`` and secrets in ``app_config.runtime_auth``.
    """
    try:
        async with _settings_session() as session:
            persisted = await SettingsRepository(session).get()
        persisted = _decrypt_user_settings(persisted)
        runtime = await _runtime_row()
        updates: dict[str, object] = {**persisted}
        _update_runtime_settings(updates)
        # Secrets are never part of the editable settings payload; apply the
        # password hash directly so a change takes effect without a restart.
        if runtime.get("auth_password_hash"):
            app.state.settings = app.state.settings.model_copy(
                update={"auth_password_hash": decrypt_or_plain(runtime["auth_password_hash"])}
            )
    except Exception as exc:  # noqa: BLE001 - settings load must not break the app
        logger.warning("user settings could not be loaded", extra={"error": str(exc)})


async def _bootstrap_auth() -> None:
    """Generate and persist auth_secret / password hash on first boot.

    ``auth_secret`` must be stable across restarts so sessions survive, so it is
    generated once and stored in the DB.  ``auth_password_hash`` is only written
    here if one was provided via environment; otherwise the built-in default
    password stays in effect until the user changes it in Settings.
    """
    from ..db.models import AppConfig as _AppConfig

    runtime = await _runtime_row()
    updates: dict[str, object] = {}
    if not runtime.get("auth_secret"):
        import secrets as _secrets

        updates["auth_secret"] = _secrets.token_urlsafe(32)
    if _settings().auth_password_hash and not runtime.get("auth_password_hash"):
        updates["auth_password_hash"] = _settings().auth_password_hash
    if updates:
        merged = {**runtime, **updates}
        # Encrypt the secrets at rest; the values stay plaintext in memory.
        if encryption_enabled():
            for _key in ("auth_secret", "auth_password_hash"):
                if isinstance(merged.get(_key), str):
                    merged[_key] = encrypt(merged[_key])
        async with _settings_session() as session, session.begin():
            row = await session.get(_AppConfig, "runtime_auth")
            if row is None:
                session.add(_AppConfig(key="runtime_auth", value=merged))
            else:
                row.value = merged
    # Apply the persisted secret (and any env-provided hash) to runtime settings.
    final = await _runtime_row()
    opts: dict[str, object] = {"auth_secret": decrypt_or_plain(final.get("auth_secret"))}
    if final.get("auth_password_hash"):
        opts["auth_password_hash"] = decrypt_or_plain(final["auth_password_hash"])
    app.state.settings = app.state.settings.model_copy(update=opts)


async def _auth_runtime_hash() -> str | None:
    runtime = await _runtime_row()
    value = runtime.get("auth_password_hash")
    return decrypt_or_plain(value) if value else None


async def _migrate_plaintext_secrets() -> None:
    """Encrypt legacy plaintext secrets now that ENCRYPTION_KEY is configured.

    Runs once at startup: any ``auth_secret``/``auth_password_hash`` in
    ``runtime_auth`` and ``exhentai_cookies``/``telegram_bot_token`` in
    ``user_settings`` still stored as plaintext are re-written encrypted.
    """
    if not encryption_enabled():
        return
    from ..db.models import AppConfig as _AppConfig

    try:
        async with _settings_session() as session, session.begin():
            runtime_row = await session.get(_AppConfig, "runtime_auth")
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
    except Exception as exc:  # noqa: BLE001 - migration must not block startup
        logger.warning("plaintext secret migration failed", extra={"error": str(exc)})


@app.on_event("startup")
async def startup() -> None:
    try:
        async with _settings_session() as session:
            persisted = await SettingsRepository(session).get()
        _update_runtime_settings(_decrypt_user_settings(persisted))
    except Exception:  # noqa: BLE001 - startup must remain usable when DB is unavailable
        logger.warning("user settings could not be loaded at startup")
    # auth_secret lives in the DB so sessions survive restarts; on the very first
    # boot it is generated here and the env-provided password hash (if any) is
    # imported once.  Every subsequent boot reads both from the DB.
    try:
        await _bootstrap_auth()
        await _migrate_plaintext_secrets()
    except Exception:  # noqa: BLE001
        logger.warning("auth bootstrap failed; using temporary credentials")
    client = EhClient(_settings(), max_concurrency=_settings().exhentai_max_concurrency)
    app.state.eh_client = client
    app.state.downloader = Downloader(
        client,
        _settings().download_root,
        concurrency=_settings().download_concurrency,
        page_concurrency=_settings().page_concurrency,
    )
    app.state.telegram = TelegramNotifier(_settings())
    _start_telegram_bot()
    app.state.favorites_service = FavoritesService(
        client, _FavoritesRepositoryProxy(), _FavoriteDownloadQueue(), app.state.telegram
    )
    app.state.favorite_poll_task = asyncio.create_task(_favorites_poll_loop())
    # Sweep leftover partial-download dirs from a previous run before the
    # download worker starts — but KEEP those that belong to pending/active
    # download tasks, so a retry (or a container restart that recovers an
    # interrupted task) resumes from the pages already on disk instead of
    # re-downloading the whole gallery. Stale dirs with no task are removed.
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
        except Exception as exc:  # noqa: BLE001 - fall back to keeping nothing
            logger.warning(
                "could not read active downloads for temp sweep",
                extra=log_extra(error=type(exc).__name__),
            )
        _root = Path(_settings().download_root)
        for _child in _root.glob(".gv-*"):
            gid_text = _child.name[len(".gv-"):] if _child.name.startswith(".gv-") else ""
            if gid_text.isdigit() and int(gid_text) in keep_gids:
                continue
            if _child.is_dir():
                _shutil.rmtree(_child, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001 - cleaning is best-effort
        logger.warning(
            "partial download cleanup failed", extra=log_extra(error=type(exc).__name__)
        )
    global download_worker_task
    download_worker_task = asyncio.create_task(_download_worker_loop())
    global download_retry_sweep_task
    download_retry_sweep_task = asyncio.create_task(_download_retry_sweep_loop())
    global telegram_flush_task
    telegram_flush_task = asyncio.create_task(_telegram_flush_loop())
    global tag_sync_worker_task
    tag_sync_worker_task = asyncio.create_task(_tag_sync_worker_loop())
    app.state.spawned_tasks = set()
    global thumb_worker_task
    thumb_worker_task = asyncio.create_task(_thumbnail_worker_loop())
    if _settings().generate_thumbnails:
        try:
            await _seed_thumbnails()
        except Exception as exc:  # noqa: BLE001 - seeding must not block boot
            logger.warning(
                "thumbnail seeding failed", extra=log_extra(error=type(exc).__name__)
            )
    _ensure_translation_updater()
    await asyncio.to_thread(load_translations)
    logger.info("GalleryVault started", extra=log_extra(library_roots=_settings().library_roots))


@app.on_event("shutdown")
async def shutdown() -> None:
    for task in list(getattr(app.state, "spawned_tasks", set()) or ()):
        task.cancel()
    for task in list(getattr(app.state, "spawned_tasks", set()) or ()):
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    if translation_update_task is not None:
        translation_update_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await translation_update_task
    poll_task = app.state.favorite_poll_task
    if poll_task is not None:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task
    if app.state.telegram_bot_task is not None:
        app.state.telegram_bot_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.telegram_bot_task
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
    if app.state.telegram is not None:
        await app.state.telegram.flush_summary()
        await app.state.telegram.aclose()
    if app.state.eh_client is not None:
        await app.state.eh_client.aclose()
    await app.state.engine.dispose()




@app.post("/login")
async def login(request: Request):
    ip = request.client.host if request.client else "unknown"
    if not await _login_gate(ip):
        logger.info(
            "login rate limited", extra=log_extra(ip=ip, reason="rate_limit")
        )
        return HTMLResponse("Too many attempts, try again later", status_code=429)
    form = parse_qs((await request.body()).decode(errors="replace"), keep_blank_values=True)
    password = form.get("password", [""])[0]
    valid = True
    if _settings().auth_required:
        valid = verify_login_password(password, _password_effective())
    if not valid:
        logger.info(
            "authentication failed",
            extra=log_extra(
                ip=request.client.host if request.client else "unknown", reason="invalid_password"
            ),
        )
        return RedirectResponse("/login?error=1", status_code=303)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        _settings().auth_cookie_name,
        create_session(_settings().auth_secret or "", _settings().auth_session_ttl),
        httponly=True,
        samesite="lax",
        secure=_settings().auth_cookie_secure,
        max_age=_settings().auth_session_ttl,
    )
    await _login_succeeded(ip)
    return response


@app.get("/login")
async def login_get() -> RedirectResponse:
    """The frontend is served separately; a GET to /login just redirects to the
    SPA root (hash-routed), keeping e.g. /login?error=1 on the frontend."""
    return RedirectResponse("/", status_code=303)


def verify_login_password(password: str, effective: str | None) -> bool:
    """Validate a password against the configured hash or legacy plaintext."""
    if effective is None:
        # No hash configured: fall back to the built-in default password.
        return password == DEFAULT_PASSWORD
    if "$" in effective and effective.startswith("pbkdf2_sha256"):
        return verify_password(password, effective)
    return hmac.compare_digest(password, effective)


@app.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(_settings().auth_cookie_name)
    return response


def _maybe_scan_after_download(result) -> None:
    """Ingest just the freshly downloaded gallery.

    A full library scan walks every root (thousands of directories), so a
    download only indexes the single gallery it just wrote — the rows are built
    straight from the download result (title/category/tags fetched from
    ExHentai during the download), not by re-parsing the directory.  If a full
    scan is already running it will pick the new gallery up anyway and this is
    a no-op.
    """
    if scan_state.get("running"):
        return
    _spawn(_ingest_downloaded_gallery(result), "download ingest")


async def _ingest_downloaded_gallery(result) -> None:
    try:
        path = Path(result.path)
        scanner = registry.for_path(path)
        if scanner is None:
            logger.warning(
                "download ingest: no scanner for path",
                extra=log_extra(path=str(path)),
            )
            return
        files = sorted(
            (
                item
                for item in path.iterdir()
                if item.is_file()
                and not item.name.startswith(".")
                and item.suffix.casefold() in IMAGE_EXTENSIONS
            ),
            key=lambda item: natural_key(item.name),
        )
        pages = [
            PageInfo(
                i,
                item.name,
                item.suffix.casefold().lstrip("."),
                item.stat().st_size,
                item.stat().st_mtime_ns,
            )
            for i, item in enumerate(files)
        ]
        tags = [
            {"namespace": ns, "name": name} for ns, name in getattr(result, "tags", ())
        ]
        gallery = GalleryMeta(
            title=result.title or path.name,
            title_jpn=result.title_jpn,
            path=path,
            storage_type=scanner.storage_type,
            pages=pages,
            gid=result.gid,
            token=getattr(result, "token", None),
            category=result.category,
            file_count=len(pages),
            file_size=sum(p.size or 0 for p in pages),
            tags=tags,
            source_meta={"title": result.title or path.name, "tags": tags},
            storage_signature=scanner.storage_signature(path),
            storage_mtime_ns=path.stat().st_mtime_ns,
            storage_size=sum(p.size or 0 for p in pages),
        )
        gallery_id = None
        async with _settings_session() as session, session.begin():
            await GalleryIngestService(session).ingest([gallery])
            if _settings().generate_thumbnails and gallery.gid is not None:
                row = await session.execute(
                    select(Gallery.id).where(Gallery.gid == gallery.gid)
                )
                gallery_id = row.scalar_one_or_none()
        if gallery_id is not None and _settings().generate_thumbnails:
            await _enqueue_job(JOB_THUMB, gallery_id)
            thumb_state["queued"] = await _jobs_count(JOB_THUMB)
        logger.info(
            "download ingested",
            extra=log_extra(gid=gallery.gid, path=str(path), pages=len(pages)),
        )
    except Exception as exc:  # noqa: BLE001 - one bad download must not crash the worker
        logger.warning(
            "download ingest failed",
            extra=log_extra(path=str(result.path), error=type(exc).__name__),
        )


def _scan_summary_message(
    last: dict, duplicates: int, duplicate_gids: list[int], lang: str = "zh"
) -> str:
    """Human-readable scan completion message for Telegram notifications."""
    return messages.scan_summary(
        last.get("persisted", 0),
        last.get("expunged", 0),
        duplicates,
        duplicate_gids,
        lang,
    )


async def _run_scan() -> None:
    async with scan_lock:
        persisted = 0
        scanned = 0
        success = 0
        errors = 0
        scan_state["running"] = True
        scan_state["completed_at"] = None
        scan_state["started_at"] = datetime.now(UTC).isoformat()
        scan_state["scanned"] = 0
        scan_state["persisted"] = 0
        scan_state["success"] = 0
        scan_state["errors"] = 0
        scan_state["last"] = None
        _clear_cancelled("scan")
        try:
            async with _settings_session() as session:
                known = await GalleryRepository(session).existing_rows(_scan_roots())
            service = LibraryService(
                _scan_roots(),
                batch_size=_settings().scan_batch_size,
                existing=known,
                duplicate_policy=_settings().duplicate_policy,
            )
            iterator = service.scan_batches(should_stop=lambda: _cancelled("scan"))
            while True:
                if _cancelled("scan"):
                    break
                batch = await run_in_threadpool(next, iterator, None)
                if batch is None:
                    break
                scanned += len(batch)
                try:
                    async with _settings_session() as session, session.begin():
                        await GalleryIngestService(session).ingest(batch)
                    persisted += len(batch)
                    success += len(batch)
                except Exception as exc:  # noqa: BLE001
                    errors += len(batch)
                    logger.error(
                        "library scan batch failed",
                        extra=log_extra(error=type(exc).__name__, batch_size=len(batch)),
                    )
                # Live progress so the UI can show scan-in-progress counts.
                scan_state["scanned"] = scanned
                scan_state["persisted"] = persisted
                scan_state["success"] = success
                scan_state["errors"] = errors
            if not _cancelled("scan"):
                async with _settings_session() as session, session.begin():
                    expunged = await GalleryRepository(session).expunge_missing(
                        _scan_roots(), service.seen_path_hashes
                    )
                scan_state["expunged"] = expunged
                # Persist duplicate-copy groups found by this scan, enriching
                # each copy's tags from the gdata cache so the cleanup page can
                # show them alongside size / page count / posted date.
                try:
                    if service.last_duplicates:
                        async with _settings_session() as session:
                            meta = await GalleryRepository(session).metadata_map(
                                [group.gid for group in service.last_duplicates]
                            )
                            for group in service.last_duplicates:
                                tags = (meta.get(group.gid) or {}).get("tags") or []
                                for copy in group.all_copies():
                                    copy.tags = [
                                        {"namespace": t["namespace"], "name": t["name"]}
                                        for t in tags
                                    ]
                        async with _settings_session() as session, session.begin():
                            await GalleryRepository(session).sync_duplicates(
                                service.last_duplicates
                            )
                    else:
                        async with _settings_session() as session, session.begin():
                            await GalleryRepository(session).sync_duplicates([])
                except Exception as exc:  # noqa: BLE001 - reporting must not fail the scan
                    logger.warning(
                        "duplicate sync failed", extra=log_extra(error=type(exc).__name__)
                    )
                scan_state["duplicates"] = len(service.last_duplicates)
                scan_state["duplicate_gids"] = [group.gid for group in service.last_duplicates]
                if _settings().auto_sync_tags:
                    try:
                        async with _settings_session() as session:
                            last_id = 0
                            while True:
                                ids = await GalleryRepository(session).pending_tag_sync_ids(
                                    1000, last_id
                                )
                                if not ids:
                                    break
                                await _enqueue_tag_sync(ids)
                                last_id = ids[-1]
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "tag sync enqueue failed", extra=log_extra(error=type(exc).__name__)
                        )
                counters = service.last_counters
                scan_state["last"] = {
                    **counters.__dict__,
                    "persisted": persisted,
                    "expunged": expunged,
                }
                logger.info("library scan persisted", extra=log_extra(**scan_state["last"]))
        except Exception as exc:  # noqa: BLE001
            scan_state["last"] = {"error": type(exc).__name__, "persisted": persisted}
            logger.error(
                "library scan persistence error", extra=log_extra(error=type(exc).__name__)
            )
        finally:
            cancelled = _cancelled("scan")
            last = scan_state["last"] or {}
            scan_state["running"] = False
            scan_state["completed_at"] = datetime.now(UTC).isoformat()
            _record_task(
                "scan",
                scan_state.get("started_at"),
                scan_state["completed_at"],
                "cancelled" if cancelled else ("failed" if last.get("error") else "success"),
                reason=(
                    "cancelled"
                    if cancelled
                    else last.get("error") if last.get("error") else ""
                ),
                done=scanned,
                total=0,
            )
            _clear_cancelled("scan")
            try:
                if not cancelled and app.state.telegram is not None and _settings().telegram_chat_ids:
                    if last.get("error"):
                        await app.state.telegram.send_message(
                            messages.scan_failed(last["error"], _settings().telegram_notify_lang)
                        )
                    else:
                        await app.state.telegram.send_message(
                            _scan_summary_message(
                                last,
                                int(scan_state.get("duplicates") or 0),
                                list(scan_state.get("duplicate_gids") or []),
                                _settings().telegram_notify_lang,
                            )
                        )
            except Exception as exc:  # noqa: BLE001 - notification must not break the scan
                logger.warning(
                    "scan notification failed", extra=log_extra(error=type(exc).__name__)
                )


def _settings_session():
    return app.state.session_factory()


# --- Persistent background-job queue (thumbnails, tag sync) ---------------
# The queue itself lives in ``background_jobs`` so queued work survives a
# restart and (later) multiple processes can claim safely.  These helpers wrap
# the repository with a short transaction per operation.
JOB_THUMB = BackgroundJobsRepository.JOB_THUMB
JOB_TAG_SYNC = BackgroundJobsRepository.JOB_TAG_SYNC


async def _jobs_count(job_type: str) -> int:
    try:
        async with _settings_session() as session:
            return await BackgroundJobsRepository(session).count(job_type)
    except Exception:  # noqa: BLE001 - stats must never break callers
        return 0


async def _claim_jobs(
    job_type: str, limit: int = 1, *, lease_seconds: int = 600
) -> list[tuple[int, int]]:
    try:
        async with _settings_session() as session, session.begin():
            return await BackgroundJobsRepository(session).claim(
                job_type, limit, lease_seconds=lease_seconds
            )
    except Exception as exc:  # noqa: BLE001 - one DB hiccup must not stop a worker
        logger.warning(
            "background job claim failed",
            extra=log_extra(job_type=job_type, error=type(exc).__name__),
        )
        return []


async def _complete_job(job_type: str, gallery_id: int) -> None:
    try:
        async with _settings_session() as session, session.begin():
            await BackgroundJobsRepository(session).complete(job_type, gallery_id)
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup
        logger.warning(
            "background job completion failed",
            extra=log_extra(job_type=job_type, gallery_id=gallery_id, error=type(exc).__name__),
        )


async def _requeue_job(
    job_type: str, gallery_id: int, *, next_attempt_at: datetime | None = None
) -> None:
    try:
        async with _settings_session() as session, session.begin():
            await BackgroundJobsRepository(session).requeue(
                job_type, gallery_id, next_attempt_at=next_attempt_at
            )
    except Exception as exc:  # noqa: BLE001 - a requeue loss is not fatal
        logger.warning(
            "background job requeue failed",
            extra=log_extra(job_type=job_type, gallery_id=gallery_id, error=type(exc).__name__),
        )


async def _enqueue_job(job_type: str, gallery_id: int) -> bool:
    try:
        async with _settings_session() as session, session.begin():
            return await BackgroundJobsRepository(session).enqueue(job_type, gallery_id)
    except Exception as exc:  # noqa: BLE001 - enqueue must not break its caller
        logger.warning(
            "background job enqueue failed",
            extra=log_extra(job_type=job_type, gallery_id=gallery_id, error=type(exc).__name__),
        )
        return False


# --- Download progress batching -------------------------------------------
# Persist progress at most every N pages or T seconds instead of once per page,
# cutting download_tasks writes on long galleries by an order of magnitude.
_PROGRESS_FLUSH_STEP = 20
_PROGRESS_FLUSH_INTERVAL = 5.0

# --- Background-job worker pacing -----------------------------------------
_THUMB_POLL_INTERVAL = 1.0
_THUMB_IDLE_SECONDS = 5.0


def _db_error(exc: Exception) -> HTTPException:
    logger.error("database operation failed", extra=log_extra(error=type(exc).__name__))
    return HTTPException(status_code=503, detail="Database is unavailable")


async def _download_progress(task_id: int, current_page: int, total_pages: int) -> None:
    try:
        async with _settings_session() as session, session.begin():
            await DownloadRepository(session).progress(task_id, current_page, total_pages)
    except SQLAlchemyError as exc:
        logger.warning(
            "download progress persistence failed", extra=log_extra(error=type(exc).__name__)
        )


async def _run_download(task: DownloadTask) -> None:
    """Keep task state in the database while the injected worker does network I/O."""
    row = None
    try:
        async with _settings_session() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row is None or row.status == "cancelled":
                return
            row.status = "downloading"
            row.started_at = datetime.now(UTC)
        # Retry ownership lives in the persistent worker. The downloader makes
        # exactly one network attempt per claimed task attempt.
        progress_state = {"last_persisted": 0, "last_flush": 0.0}

        async def _on_progress(current: int, total: int) -> None:
            if task.id is not None and task.id in _download_cancelled:
                raise DownloadCancelledError("download was cancelled")
            # Batch the DB writes: at most one commit per page on short
            # galleries, throttled to one every 20 pages / 5s on long ones.
            # The first write always lands so the UI shows progress at once.
            now = _time.monotonic()
            if (
                current >= total
                or progress_state["last_persisted"] == 0
                or current - progress_state["last_persisted"] >= _PROGRESS_FLUSH_STEP
                or now - progress_state["last_flush"] >= _PROGRESS_FLUSH_INTERVAL
            ):
                await _download_progress(task.id, current, total)
                progress_state["last_persisted"] = current
                progress_state["last_flush"] = now

        result = await app.state.downloader.execute(
            DownloadTask(
                task.gid,
                task.token,
                task.title,
                task.id,
                1,
                task.mode,
                task.category,
                max_pages=task.max_pages,
            ),
            progress=_on_progress,
        )
        completed = False
        async with _settings_session() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row is not None:
                # A cancel can land between the last progress check and this
                # commit (the cancel route flips the DB status and sets the
                # in-flight flag).  Honor it: walk the cancel cleanup path
                # below instead of racing it and marking the task success.
                if row.status == "cancelled" or (
                    task.id is not None and task.id in _download_cancelled
                ):
                    raise DownloadCancelledError("download was cancelled")
                row.status, row.target_path, row.category = (
                    "success",
                    str(result.path),
                    result.category,
                )
                row.error_message = None
                row.retry_count = 0
                row.retry_at = None
                row.finished_at = datetime.now(UTC)
                # Skip the attempt log when the task row was deleted mid-flight
                # (writing one would violate the FK on download_tasks.id).
                await DownloadRepository(session).record_attempt(
                    task.id or 0, row.retry_count + 1, "success"
                )
                completed = True
        # The success path always consumes the in-flight flag, so a cancel that
        # lands just after the commit above can never leak into a later retry.
        if task.id is not None:
            _download_cancelled.discard(task.id)
        if completed:
            await _record_download_notification("ok", result.title or task.gid, str(result.pages))
            _maybe_scan_after_download(result)
    except DownloadCancelledError:
        # The user cancelled mid-flight: drop the partial temp dir and leave
        # the task cancelled (do not retry or mark failed).
        try:
            temp = Path(_settings().download_root) / f".gv-{task.gid}"
            if temp.exists():
                import shutil as _shutil

                _shutil.rmtree(temp, ignore_errors=True)
        except OSError:
            pass
        _download_cancelled.discard(task.id)
        logger.info("download cancelled", extra=log_extra(gid=task.gid))
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "download task failed", extra=log_extra(gid=task.gid, error=type(exc).__name__)
        )
        try:
            async with _settings_session() as session, session.begin():
                row = await session.get(DownloadTaskModel, task.id)
                if row and row.status != "cancelled":
                    now = datetime.now(UTC)
                    # A dead ExHentai session is not going to heal on its own;
                    # fail immediately instead of burning max_retries of
                    # pointless network round-trips against a redirect loop.
                    auth_failure = "authenticat" in str(exc)
                    # The remoteapi.php anti-bot challenge is temporary (IP
                    # rate-challenge), and so are the connection resets that the
                    # challenged node returns; schedule the retry with an
                    # exponential backoff so the burst passes and the download
                    # resumes instead of hammering ExHentai in a tight loop.
                    challenge = (
                        "challeng" in str(exc)
                        or "disconnect" in str(exc)
                        or "reset" in str(exc)
                        or isinstance(
                            exc, (EhClientError, asyncio.TimeoutError)
                        )
                    )
                    row.retry_count += 1
                    if auth_failure or row.retry_count >= row.max_retries:
                        row.status = "failed"
                        row.retry_at = None
                        row.finished_at = now
                    else:
                        # Backoff is enforced by the claim worker via retry_at,
                        # so concurrent workers cannot steal a task early.
                        row.status = "pending"
                        row.retry_at = (
                            now + timedelta(seconds=_retry_backoff(row.retry_count))
                            if challenge
                            else now
                        )
                    row.error_message = f"{type(exc).__name__}: {exc}"
                    row.updated_at = now
                    await DownloadRepository(session).record_attempt(
                        task.id or 0, row.retry_count, "failed", type(exc).__name__
                    )
            if row is not None and row.status == "failed":
                await _record_download_notification(
                    "fail", task.title or task.gid, type(exc).__name__
                )
        except SQLAlchemyError as db_exc:
            logger.error(
                "download status persistence failed", extra=log_extra(error=type(db_exc).__name__)
            )


_TELEGRAM_FLUSH_INTERVAL = 60.0


async def _record_download_notification(
    kind: str, title: str, detail: str | None = None
) -> None:
    """Record a download terminal event for Telegram.

    In ``summary`` mode the event is buffered and flushed as a digest as soon as
    the download queue is idle (so a single download still reports immediately,
    while a bulk run collapses into one message instead of one per gallery).
    """
    notifier = app.state.telegram
    if notifier is None:
        return
    await notifier.record_download_outcome(kind, title, detail)
    if _settings().telegram_notify_level != "summary" or not notifier.pending_events:
        return
    try:
        async with _settings_session() as session:
            active = await DownloadRepository(session).count_active()
        if active == 0:
            await notifier.flush_summary()
    except SQLAlchemyError as exc:
        logger.warning(
            "telegram summary flush check failed", extra=log_extra(error=type(exc).__name__)
        )


async def _telegram_flush_loop() -> None:
    """Flush a non-empty Telegram download digest on a timer as a fallback.

    The primary trigger is the queue going idle; this catches a long run where
    a task is stuck in ``downloading`` (so no idle event ever fires) without
    splitting an active batch into premature partial digests: only buffers that
    have received **no new events** for the interval are flushed.
    """
    while True:
        await asyncio.sleep(_TELEGRAM_FLUSH_INTERVAL)
        notifier = app.state.telegram
        if notifier is not None:
            try:
                if notifier.events_stale(_TELEGRAM_FLUSH_INTERVAL):
                    await notifier.flush_summary()
            except Exception as exc:  # noqa: BLE001 - timer must not crash the app
                logger.warning(
                    "telegram summary flush failed", extra=log_extra(error=type(exc).__name__)
                )


async def _download_worker_loop() -> None:
    """Recover and claim persisted jobs, so a process restart does not lose work."""
    try:
        async with _settings_session() as session, session.begin():
            await DownloadRepository(session).recover_orphans()
    except Exception as exc:  # noqa: BLE001 - worker must survive database outages
        logger.warning("download recovery failed", extra=log_extra(error=type(exc).__name__))
    # Run `download_concurrency` claim loops in parallel. claim_pending uses
    # FOR UPDATE SKIP LOCKED so the workers never hand out the same task, and
    # Downloader.semaphore keeps the actual page concurrency bounded.
    concurrency = max(1, _settings().download_concurrency)

    async def _worker() -> None:
        while True:
            try:
                async with _settings_session() as session, session.begin():
                    row = await DownloadRepository(session).claim_pending()
                    if row is not None:
                        task = DownloadTask(
                            row.gid,
                            row.token,
                            row.title or str(row.gid),
                            row.id,
                            row.max_retries,
                            row.mode,
                            row.category or "other",
                            max_pages=row.max_pages,
                        )
                if row is not None:
                    await _run_download(task)
                else:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one task must not stop the worker
                logger.error(
                    "download worker iteration failed", extra=log_extra(error=type(exc).__name__)
                )
                await asyncio.sleep(2)

    workers = [asyncio.create_task(_worker()) for _ in range(concurrency)]
    try:
        await asyncio.gather(*workers)
    finally:
        pass  # workers run until cancelled at shutdown


_RETRY_BACKOFFS = (
    30, 120, 480, 1800, 3600, 7200, 10800, 14400, 18000, 21600,
)
# 30s, 2m, 8m, 30m, 1h, 2h, 3h, 4h, 5h, 6h — one slot per retry_count (1-based).


def _retry_backoff(retry_count: int) -> int:
    """Return the backoff delay (seconds) for the given failed attempt count."""
    return _RETRY_BACKOFFS[min(max(1, retry_count) - 1, len(_RETRY_BACKOFFS) - 1)]


_DOWNLOAD_RETRY_SWEEP_INTERVAL = 60.0


async def _download_retry_sweep_loop() -> None:
    """Auto-requeue failed downloads that still have retry budget left.

    A failed task re-enters the queue on its own via ``retry_at`` until the
    budget is exhausted; this sweep catches tasks that failed before the
    scheduling logic existed (or that were manually retried and re-failed), so
    they are not stuck waiting for a user click.
    """
    while True:
        await asyncio.sleep(_DOWNLOAD_RETRY_SWEEP_INTERVAL)
        try:
            async with _settings_session() as session, session.begin():
                rearmed = await DownloadRepository(session).rearm_failed()
            if rearmed:
                logger.info(
                    "rearmed failed download tasks", extra=log_extra(count=rearmed)
                )
        except Exception as exc:  # noqa: BLE001 - sweep must not crash the app
            logger.warning(
                "download retry sweep failed", extra=log_extra(error=type(exc).__name__)
            )


async def _enqueue_tag_sync(gallery_ids: list[int]) -> int:
    """Queue gallery ids for background tag synchronization, de-duplicating."""
    added = 0
    for start in range(0, len(gallery_ids), 500):
        chunk = gallery_ids[start : start + 500]
        async with _settings_session() as session, session.begin():
            added += await BackgroundJobsRepository(session).enqueue_many(JOB_TAG_SYNC, chunk)
    if added:
        current = int(tag_sync_state["total"] or 0)
        tag_sync_state["total"] = current + added
        tag_sync_state["queued"] = await _jobs_count(JOB_TAG_SYNC)
    return added


_TRANSLATION_REPO = "EhTagTranslation/Database"
_TRANSLATION_RELEASE_API = f"https://api.github.com/repos/{_TRANSLATION_REPO}/releases/latest"


async def _translation_download_url(client: httpx.AsyncClient) -> str:
    """Resolve the db.text.json asset URL of the latest release."""
    response = await client.get(
        _TRANSLATION_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "GalleryVault"},
    )
    response.raise_for_status()
    assets = response.json().get("assets", [])
    for asset in assets:
        if asset.get("name") == "db.text.json":
            return asset["browser_download_url"]
    raise RuntimeError("db.text.json asset not found in the latest release")


async def _fetch_translation_db() -> object:
    """Download the latest EhTagTranslation / ehsyringe database."""
    proxy = _settings().socks5_proxy or _settings().http_proxy
    async with httpx.AsyncClient(timeout=30, proxy=proxy, follow_redirects=True) as client:
        url = await _translation_download_url(client)
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def _translation_update_once() -> bool:
    """Download, merge and reset the live translation table. Returns success."""
    if not translation_state["running"]:
        translation_state["started_at"] = datetime.now(UTC).isoformat()
        translation_state["history_recorded"] = False
    translation_state["running"] = True
    ok = False
    try:
        data = await _fetch_translation_db()
        # Building the translation table is regex/JSON heavy: run it off the
        # event loop so an update never stalls API responses.
        def _apply_translations() -> int:
            load_translations(reset=True)
            return merge_translation_data(data)

        entries = await asyncio.to_thread(_apply_translations)
        translation_state["entries"] = entries
        translation_state["last"] = datetime.now(UTC).isoformat()
        translation_state["last_error"] = None
        logger.info("tag translations updated", extra=log_extra(entries=entries))
        ok = True
    except Exception as exc:  # noqa: BLE001 - a failed refresh must not stop the loop
        translation_state["last_error"] = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "tag translation update failed", extra=log_extra(error=type(exc).__name__)
        )
    finally:
        translation_state["running"] = False
        translation_state["completed_at"] = datetime.now(UTC).isoformat()
        if not translation_state["history_recorded"]:
            translation_state["history_recorded"] = True
            _record_task(
                "translation",
                translation_state.get("started_at"),
                translation_state["completed_at"],
                "success" if ok else "failed",
                reason=translation_state.get("last_error") or "",
                done=int(translation_state.get("entries") or 0),
                total=0,
            )
    return ok


async def _translation_update_loop() -> None:
    while True:
        minutes = int(_settings().tag_translation_update_interval_minutes)
        if minutes <= 0:
            await asyncio.sleep(3600)
            continue
        try:
            await _translation_update_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("tag translation loop error", extra={"error": str(exc)})
            translation_state["last_error"] = str(exc)
        # Sleep in small slices so shutdown can interrupt promptly.
        deadline = asyncio.get_event_loop().time() + minutes * 60
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(min(1, max(0.1, deadline - asyncio.get_event_loop().time())))


def _ensure_translation_updater() -> asyncio.Task:
    if (
        translation_update_task is None or translation_update_task.done()
    ) and _settings().tag_translation_update_interval_minutes > 0:
        globals()["translation_update_task"] = asyncio.create_task(_translation_update_loop())
    return translation_update_task


async def _tag_sync_worker_loop() -> None:
    """Synchronize tags from ExHentai in the background.

    A bounded pool of concurrent workers drains the queue so a scan of hundreds
    of thousands of galleries makes progress quickly, while ``asyncio.sleep``
    still paces each worker. On ExHentai throttling (``EhClientError`` /
    timeouts) the worker backs off exponentially and retries the gallery, so we
    avoid a ban instead of hammering a rate-limited endpoint.
    """
    logger.info("tag sync worker started")
    # Reopen jobs whose claiming worker died before completing them.
    try:
        async with _settings_session() as session, session.begin():
            await BackgroundJobsRepository(session).mark_stale()
    except Exception as exc:  # noqa: BLE001 - recovery must not kill the worker
        logger.warning(
            "tag sync stale-recovery failed", extra=log_extra(error=type(exc).__name__)
        )
    try:
        async with _settings_session() as session:
            last_id = 0
            seeded = 0
            while True:
                ids = await GalleryRepository(session).pending_tag_sync_ids(1000, last_id)
                if not ids:
                    break
                await _enqueue_tag_sync(ids)
                seeded += len(ids)
                last_id = ids[-1]
            tag_sync_state["total"] = seeded + tag_sync_state["processed"]
    except Exception as exc:  # noqa: BLE001 - seeding must not kill the worker
        logger.warning("tag sync seeding failed", extra=log_extra(error=type(exc).__name__))
    tag_sync_state["queued"] = await _jobs_count(JOB_TAG_SYNC)
    logger.info("tag sync seeded", extra=log_extra(queued=tag_sync_state["queued"]))
    tag_sync_state["running"] = True
    tag_sync_state["completed_at"] = None
    concurrency = max(1, _settings().tag_sync_concurrency)
    semaphore = asyncio.Semaphore(concurrency)
    base_interval = max(0.1, float(_settings().tag_sync_interval_seconds))
    interval = [base_interval]
    success_streak = [0]
    last_activity = [_time.monotonic()]
    MAX_BACKOFF = 60.0
    MAX_ATTEMPTS = 8
    MAX_TAG_SYNC_HOLDS = 120
    _TAG_SYNC_IDLE_SECONDS = 5.0

    async def _sync_one(gallery_id: int, attempts: int) -> bool | None:
        try:
            # Coordination with the favorites check: while a folder check is
            # running, its gdata batches are populating the metadata cache. A
            # gallery that isn't cached yet would otherwise be fetched one by
            # one from ExHentai — a redundant network call the batch is about
            # to cover. Hold such galleries (re-queue, retry shortly) until the
            # check finishes; give up after MAX_TAG_SYNC_HOLDS so galleries
            # that simply aren't in any favorite folder still sync.
            if favorites_check_state.get("running"):
                holds = tag_sync_holds.get(gallery_id, 0)
                cached_tags = False
                if holds < MAX_TAG_SYNC_HOLDS:
                    async with _settings_session() as session:
                        repo = GalleryRepository(session)
                        gallery = await repo.get_for_tag_sync(gallery_id)
                        if gallery is not None and gallery.gid is not None:
                            cached = await repo.metadata_for_gid(gallery.gid)
                            cached_tags = bool(cached and cached.get("tags"))
                    if not cached_tags:
                        tag_sync_holds[gallery_id] = holds + 1
                        await _requeue_job(
                            JOB_TAG_SYNC,
                            gallery_id,
                            next_attempt_at=datetime.now(UTC) + timedelta(seconds=60),
                        )
                        tag_sync_state["queued"] = await _jobs_count(JOB_TAG_SYNC)
                        await asyncio.sleep(interval[0])
                        return False
                tag_sync_holds.pop(gallery_id, None)
            # Phase 1: read the gallery row + fetch metadata, WITHOUT holding a
            # DB transaction across the ExHentai round-trip.
            async with _settings_session() as session:
                plan = await TagSyncService(
                    app.state.eh_client, GalleryRepository(session)
                ).fetch_plan(gallery_id)
            # Phase 2: persist in a short transaction.
            async with _settings_session() as session, session.begin():
                await TagSyncService(
                    app.state.eh_client, GalleryRepository(session)
                ).apply_plan(gallery_id, plan)
            tag_sync_state["succeeded"] += 1
            await _complete_job(JOB_TAG_SYNC, gallery_id)
            success_streak[0] += 1
            if success_streak[0] >= 10 and interval[0] > base_interval:
                interval[0] = max(base_interval, interval[0] / 2)
            return True
        except GalleryGoneError as exc:
            # "Not found" covers two very different cases: the gallery was
            # actually deleted from ExHentai, or the configured site (the
            # public e-hentai.org mirror) simply cannot see an ExHentai-only
            # gallery. Only the former is a deletion — on the public mirror we
            # suspend the gallery instead of reclassifying it, and the settings
            # save handler resumes it once the base URL is back on ExHentai.
            if _is_public_site(_settings().exhentai_base_url):
                try:
                    async with _settings_session() as session, session.begin():
                        await GalleryRepository(session).mark_tag_not_visible(gallery_id)
                except Exception:  # noqa: BLE001 - marking is best-effort
                    logger.warning(
                        "could not mark gallery not-visible on public mirror",
                        extra=log_extra(gallery_id=gallery_id),
                    )
            else:
                # The gallery was deleted from ExHentai; nothing can be synced.
                # Mark it done so it stops cluttering the pending queue, without
                # treating it as a transient failure (no retries / no backoff).
                try:
                    async with _settings_session() as session, session.begin():
                        await GalleryRepository(session).mark_tag_synced(
                            gallery_id, category="deleted"
                        )
                except Exception:  # noqa: BLE001 - marking is best-effort
                    logger.warning(
                        "could not mark deleted gallery synced",
                        extra=log_extra(gallery_id=gallery_id),
                    )
            await _complete_job(JOB_TAG_SYNC, gallery_id)
            tag_sync_state["failed"] += 1
            logger.warning(
                "tag sync skipped (gallery gone)",
                extra=log_extra(gallery_id=gallery_id, error=str(exc)),
            )
        except Exception as exc:  # noqa: BLE001 - one gallery must not stop the worker
            tag_sync_state["failed"] += 1
            tag_sync_state["last_error"] = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "tag sync failed",
                extra=log_extra(gallery_id=gallery_id, error=type(exc).__name__),
            )
            if isinstance(exc, (EhClientError, asyncio.TimeoutError)):
                interval[0] = min(MAX_BACKOFF, interval[0] * 2)
                success_streak[0] = 0
                if attempts < MAX_ATTEMPTS:
                    tag_sync_state["retries"] += 1
                    # attempt counter lives in the job row, so a restart does
                    # not reset it and a poisoned gallery stops retrying.
                    await _requeue_job(JOB_TAG_SYNC, gallery_id)
                    return
            # Retries are exhausted for a persistently failing gallery; mark it
            # attempted so it stops re-seeding the queue on every restart.
            try:
                async with _settings_session() as session, session.begin():
                    await GalleryRepository(session).mark_tag_synced(gallery_id)
            except Exception:  # noqa: BLE001 - marking is best-effort
                logger.warning(
                    "could not mark failed gallery synced",
                    extra=log_extra(gallery_id=gallery_id),
                )
            await _complete_job(JOB_TAG_SYNC, gallery_id)

    async def _worker() -> None:
        while True:
            if _cancelled("tag-sync"):
                break
            claimed = await _claim_jobs(JOB_TAG_SYNC, 1)
            if not claimed:
                # Queue empty: reflect idle once the queue has been empty for a
                # few seconds (mirrors the old wait_for(5s) timeouts).
                if (
                    _time.monotonic() - last_activity[0] >= _TAG_SYNC_IDLE_SECONDS
                    and tag_sync_state["running"]
                ):
                    tag_sync_state["completed_at"] = datetime.now(UTC).isoformat()
                    tag_sync_state["queued"] = await _jobs_count(JOB_TAG_SYNC)
                    tag_sync_state["running"] = False
                    if (
                        tag_sync_state.get("started_at")
                        and not tag_sync_state["history_recorded"]
                    ):
                        tag_sync_state["history_recorded"] = True
                        _record_task(
                            "tag-sync",
                            tag_sync_state.get("started_at"),
                            tag_sync_state["completed_at"],
                            "success",
                            reason=(
                                f"ok {tag_sync_state.get('succeeded', 0)} "
                                f"/ fail {tag_sync_state.get('failed', 0)}"
                            ),
                            done=int(tag_sync_state.get("processed") or 0),
                            total=int(tag_sync_state.get("total") or 0),
                        )
                await asyncio.sleep(1)
                continue
            gallery_id, attempts = claimed[0]
            last_activity[0] = _time.monotonic()
            if not tag_sync_state["running"] or not tag_sync_state.get("started_at"):
                tag_sync_state["running"] = True
                tag_sync_state["completed_at"] = None
                tag_sync_state["started_at"] = datetime.now(UTC).isoformat()
                tag_sync_state["history_recorded"] = False
            async with semaphore:
                done = await _sync_one(gallery_id, attempts)
            if done is not False:
                tag_sync_state["processed"] += 1
            tag_sync_state["queued"] = await _jobs_count(JOB_TAG_SYNC)
            tag_sync_state["interval"] = interval[0]
            await asyncio.sleep(interval[0])

    workers = [asyncio.create_task(_worker()) for _ in range(concurrency)]
    try:
        await asyncio.gather(*workers)
    finally:
        tag_sync_state["running"] = False
        if _cancelled("tag-sync"):
            tag_sync_state["completed_at"] = datetime.now(UTC).isoformat()
            if not tag_sync_state["history_recorded"]:
                tag_sync_state["history_recorded"] = True
                _record_task(
                    "tag-sync",
                    tag_sync_state.get("started_at"),
                    tag_sync_state["completed_at"],
                    "cancelled",
                    reason="cancelled",
                    done=int(tag_sync_state.get("processed") or 0),
                    total=int(tag_sync_state.get("total") or 0),
                )
            _clear_cancelled("tag-sync")


async def _category_refresh_once() -> int:
    """Backfill the 大分类 for galleries stuck in ``other``.

    These were tag-synced before category write-back existed.  Each is
    re-fetched once (paced through the tag-sync worker) and its category is
    corrected; galleries that 404 are reclassified as ``deleted``.
    """
    tag_sync_state["category_refresh_running"] = True
    refreshed = 0
    try:
        async with _settings_session() as session:
            last_id = 0
            ids: list[int] = []
            while True:
                batch = await GalleryRepository(session).pending_category_refresh_ids(500, last_id)
                if not batch:
                    break
                ids.extend(batch)
                last_id = batch[-1]
        for gallery_id in ids:
            try:
                async with _settings_session() as session, session.begin():
                    await TagSyncService(
                        app.state.eh_client, GalleryRepository(session)
                    ).refresh_category(gallery_id)
                refreshed += 1
            except GalleryGoneError:
                if _is_public_site(_settings().exhentai_base_url):
                    try:
                        async with _settings_session() as session, session.begin():
                            await GalleryRepository(session).mark_tag_not_visible(gallery_id)
                    except Exception as exc:  # noqa: BLE001 - best-effort
                        logger.warning(
                            "could not mark gallery not-visible during category refresh",
                            extra=log_extra(gallery_id=gallery_id, error=type(exc).__name__),
                        )
                else:
                    try:
                        async with _settings_session() as session, session.begin():
                            await GalleryRepository(session).mark_tag_synced(
                                gallery_id, category="deleted"
                            )
                    except Exception as exc:  # noqa: BLE001 - best-effort
                        logger.warning(
                        "could not mark deleted gallery during category refresh",
                        extra=log_extra(gallery_id=gallery_id, error=type(exc).__name__),
                    )
            except EhClientError:
                # Transient upstream failure: skip this round, will retry later.
                logger.warning(
                    "category refresh failed",
                    extra=log_extra(gallery_id=gallery_id, error="EhClientError"),
                )
            except Exception as exc:  # noqa: BLE001 - one gallery must not stop the backfill
                logger.warning(
                    "category refresh error",
                    extra=log_extra(gallery_id=gallery_id, error=type(exc).__name__),
                )
            if gallery_id != ids[-1]:
                await asyncio.sleep(0.3)  # pace requests to ExHentai
        tag_sync_state["category_refreshed"] += refreshed
    finally:
        tag_sync_state["category_refresh_running"] = False
    return refreshed


class DownloadRequest(BaseModel):
    url: str | None = None
    gid: int | None = Field(default=None, gt=0)
    token: str | None = None
    title: str | None = None
    mode: str | None = None
    max_pages: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid_source(self) -> "DownloadRequest":
        if self.url:
            try:
                gid, token = parse_gallery_url(self.url)
            except (ValueError, TypeError) as exc:
                raise ValueError(str(exc)) from exc
            object.__setattr__(self, "gid", gid)
            object.__setattr__(self, "token", token)
        if not self.gid or not self.token:
            raise ValueError("url or gid and token is required")
        return self


class FavoriteCategoryRequest(BaseModel):
    favcat: int | None = Field(default=None, ge=0, le=9)
    enabled: bool | None = None
    mode: str | None = None

    @model_validator(mode="after")
    def valid_mode(self) -> "FavoriteCategoryRequest":
        if self.mode is not None and self.mode not in {"monitor_only", "incremental", "force"}:
            raise ValueError("invalid favorites mode")
        return self


class SettingsRequest(BaseModel):
    library_roots: list[str] | str | None = None
    exhentai_base_url: str | None = None
    exhentai_cookies: dict[str, str] | None = None
    http_proxy: str | None = None
    socks5_proxy: str | None = None
    download_root: str | None = None
    download_concurrency: int | None = Field(default=None, ge=1, le=32)
    page_concurrency: int | None = Field(default=None, ge=1, le=16)
    download_quality: str | None = None
    download_title: str | None = None
    use_hah: bool | None = None
    image_download_timeout_seconds: int | None = Field(default=None, ge=1)
    image_slow_warmup_seconds: int | None = Field(default=None, ge=1)
    image_min_speed_kb_s: int | None = Field(default=None, ge=1)
    title_display: str | None = None
    favorites_categories: list[int] | None = None
    download_favorites_enabled: bool | None = None
    favorites_poll_interval_minutes: int | None = Field(default=None, ge=1)
    favorites: list[dict[str, object]] | None = None
    ipb_member_id: str | None = None
    ipb_pass_hash: str | None = None
    igneous: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_ids: list[str] | None = None
    telegram_allowed_user_ids: list[int] | None = None
    telegram_notify_level: str | None = None
    telegram_notify_lang: str | None = None
    auto_sync_tags: bool | None = None
    tag_sync_interval_seconds: float | None = Field(default=None, gt=0)
    tag_sync_concurrency: int | None = Field(default=None, ge=1, le=32)
    generate_thumbnails: bool | None = None
    duplicate_policy: str | None = None
    auth_required: bool | None = None

    @model_validator(mode="after")
    def validate_values(self) -> "SettingsRequest":
        if self.http_proxy and self.socks5_proxy:
            raise ValueError("configure only one proxy")
        if self.favorites_categories is not None and any(
            category not in range(10) for category in self.favorites_categories
        ):
            raise ValueError("favorites categories must be between 0 and 9")
        if self.telegram_notify_level is not None and self.telegram_notify_level not in {
            "summary",
            "immediate",
            "failures_only",
            "off",
        }:
            raise ValueError(
                "telegram_notify_level must be 'summary', 'immediate', 'failures_only', or 'off'"
            )
        if self.telegram_notify_lang is not None and self.telegram_notify_lang not in {"zh", "en"}:
            raise ValueError("telegram_notify_lang must be 'zh' or 'en'")
        from ..services.duplicate_resolver import DUPLICATE_POLICIES

        if self.duplicate_policy is not None and self.duplicate_policy not in DUPLICATE_POLICIES:
            raise ValueError(
                f"duplicate_policy must be one of {', '.join(DUPLICATE_POLICIES)}"
            )
        return self


def _settings_public() -> dict[str, object]:
    current = _settings()
    return {
        "library_roots": current.library_roots,
        "library_root_warnings": library_root_warnings(current.library_roots),
        "exhentai_base_url": current.exhentai_base_url,
        "exhentai_cookie_names": sorted(current.exhentai_cookies),
        "exhentai_cookie_configured": bool(current.exhentai_cookies),
        "http_proxy": current.http_proxy,
        "socks5_proxy": current.socks5_proxy,
        "download_root": current.download_root,
        "download_concurrency": current.download_concurrency,
        "page_concurrency": current.page_concurrency,
        "download_quality": current.download_quality,
        "download_title": current.download_title,
        "use_hah": current.use_hah,
        "image_download_timeout_seconds": current.image_download_timeout_seconds,
        "image_slow_warmup_seconds": current.image_slow_warmup_seconds,
        "image_min_speed_kb_s": current.image_min_speed_kb_s,
        "title_display": current.title_display,
        "download_max_retries": 10,
        "favorites_categories": current.favorites_categories,
        "download_favorites_enabled": current.download_favorites_enabled,
        "favorites_poll_interval_minutes": current.favorites_poll_interval_minutes,
        "telegram_bot_configured": bool(current.telegram_bot_token),
        "telegram_chat_ids": current.telegram_chat_ids,
        "telegram_allowed_user_ids": current.telegram_allowed_user_ids,
        "telegram_notify_level": current.telegram_notify_level,
        "telegram_notify_lang": current.telegram_notify_lang,
        "auto_sync_tags": current.auto_sync_tags,
        "tag_sync_interval_seconds": current.tag_sync_interval_seconds,
        "tag_sync_concurrency": current.tag_sync_concurrency,
        "generate_thumbnails": current.generate_thumbnails,
        "duplicate_policy": current.duplicate_policy,
        "thumbnail_cache_dir": current.thumbnail_cache_dir,
        "auth_required": current.auth_required,
        "auth_hash_configured": _auth_hash_configured(),
        "must_change_password": _must_change_password(),
    }


def _update_runtime_settings(values: dict[str, object]) -> None:
    if (
        "favorites_poll_interval_seconds" in values
        and "favorites_poll_interval_minutes" not in values
    ):
        values = dict(values)
        values["favorites_poll_interval_minutes"] = max(
            1, round(int(values.pop("favorites_poll_interval_seconds")) / 60)
        )
    allowed = {
        "library_roots",
        "exhentai_base_url",
        "exhentai_cookies",
        "http_proxy",
        "socks5_proxy",
        "download_root",
        "download_concurrency",
        "page_concurrency",
        "download_quality",
        "download_title",
        "use_hah",
        "image_download_timeout_seconds",
        "image_slow_warmup_seconds",
        "image_min_speed_kb_s",
        "title_display",
        "favorites_categories",
        "favorites_poll_interval_minutes",
        "telegram_bot_token",
        "telegram_chat_ids",
        "telegram_allowed_user_ids",
        "telegram_notify_level",
        "telegram_notify_lang",
        "auto_sync_tags",
        "tag_sync_interval_seconds",
        "tag_sync_concurrency",
        "download_favorites_enabled",
        "auth_required",
        "tag_translation_update_interval_minutes",
        "generate_thumbnails",
        "duplicate_policy",
    }
    updates = {key: value for key, value in values.items() if key in allowed}
    if "library_roots" in updates:
        updates["library_roots"] = normalize_library_roots(updates["library_roots"])
    current = _settings()
    # model_copy(update=...) skips pydantic validation, so a stored value like a
    # plaintext JSON string in exhentai_cookies would stay a string and crash
    # EhClient's dict(cookies). Re-validate the merged settings instead so
    # strings are parsed back into their typed values (no ENCRYPTION_KEY case).
    app.state.settings = type(current).model_validate({**current.model_dump(), **updates})




async def _refresh_services() -> None:
    """Rebuild network-bound services so changed proxy/cookies apply immediately."""
    old_client = app.state.eh_client
    old_telegram = app.state.telegram
    if old_telegram is not None:
        await old_telegram.flush_summary()
        await old_telegram.aclose()
    if old_client is not None:
        await old_client.aclose()
    client = EhClient(_settings(), max_concurrency=_settings().exhentai_max_concurrency)
    app.state.eh_client = client
    app.state.downloader = Downloader(
        client,
        _settings().download_root,
        concurrency=_settings().download_concurrency,
        page_concurrency=_settings().page_concurrency,
    )
    app.state.telegram = TelegramNotifier(_settings())
    _start_telegram_bot()
    app.state.favorites_service = FavoritesService(
        client, _FavoritesRepositoryProxy(), _FavoriteDownloadQueue(), app.state.telegram
    )
    _ensure_translation_updater()


def _start_telegram_bot() -> None:
    """(Re)start the Telegram long-polling bot using the current notifier client.

    Must be called whenever ``app.state.telegram`` is rebuilt, otherwise the old
    bot keeps polling through a closed client and logs RuntimeError every loop.
    """
    if app.state.telegram_bot_task is not None:
        app.state.telegram_bot_task.cancel()
    if _settings().telegram_bot_token:
        app.state.telegram_bot_task = asyncio.create_task(
            TelegramBotService(
                _settings(),
                client=app.state.telegram.client,
                queue=_FavoriteDownloadQueue(),
                notifier=app.state.telegram,
            ).run()
        )
    else:
        app.state.telegram_bot_task = None




class _FavoritesRepositoryProxy:
    async def _call(self, method: str, *args):
        async with _settings_session() as session, session.begin():
            return await getattr(FavoritesRepository(session), method)(*args)

    async def known_gids(self, favcat: int):
        return await self._call("known_gids", favcat)

    async def existing_gallery_gids(self, gids: list[int]):
        return await self._call("existing_gallery_gids", gids)

    async def remember(self, favcat: int, item):
        return await self._call("remember", favcat, item)

    async def remember_many(self, favcat: int, items):
        return await self._call("remember_many", favcat, items)

    async def prune(self, favcat: int, current_gids: set[int]):
        return await self._call("prune", favcat, current_gids)

    async def checked(self, favcat: int, success: bool):
        return await self._call("checked", favcat, success)

    async def category(self, favcat: int):
        return await self._call("category", favcat)


class _FavoriteDownloadQueue:
    async def enqueue(self, item) -> bool:
        async with _settings_session() as session, session.begin():
            task = await DownloadRepository(session).create(
                item.gid, item.token, item.title, "favorite"
            )
            if task is None:
                return False
        logger.info("favorite download persisted", extra=log_extra(gid=item.gid, task_id=task.id))
        return True


def _spawn(coroutine, operation: str) -> None:
    async def guarded() -> None:
        try:
            await coroutine
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "background task failed",
                extra=log_extra(operation=operation, error=type(exc).__name__),
            )

    task = asyncio.create_task(guarded())
    spawned = getattr(app.state, "spawned_tasks", None)
    if spawned is not None:
        spawned.add(task)
        task.add_done_callback(spawned.discard)









class FavoritesRemoveRequest(BaseModel):
    gids: list[int]
    delete_local: bool = False




async def _run_duplicates_scan() -> None:
    duplicates_state.update({"running": True, "stage": "reading", "done": 0, "total": 0, "last_error": None, "groups": []})
    try:
        async with _settings_session() as session:
            items = await FavoritesRepository(session).all_items()
            gids = list({item[1] for item in items})
            duplicates_state["total"] = len(items)
            duplicates_state["stage"] = "analyzing"
            gallery_titles = await FavoritesRepository(session).gallery_titles_by_gid(gids)
            duplicates_state["done"] = len(items)
            duplicates_state["stage"] = "grouping"
            groups = find_duplicate_groups(items, gallery_titles=gallery_titles)
            group_items = [it for g in groups for it in g["items"]]
            local_ids = [it["gallery_id"] for it in group_items if it["gallery_id"] is not None]
            tag_map = await FavoritesRepository(session).tags_for_gallery_ids(local_ids)
            cloud_pairs = [
                (it["gid"], it["token"]) for it in group_items if it["gallery_id"] is None
            ]
            duplicates_state["stage"] = "enriching"
            gmeta = await _favorites_metadata(cloud_pairs) if cloud_pairs else {}
            for it in group_items:
                if it["gallery_id"] is not None:
                    en_title, jp_title = gallery_titles.get(it["gid"], (None, None))
                    it["title_jpn"] = jp_title
                    it["display_title"] = (
                        resolve_display_title(en_title or it.get("title"), jp_title)
                        or it.get("title") or f"gid {it['gid']}"
                    )
                    it["tags"] = [
                        {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
                        for ns, name in tag_map.get(it["gallery_id"], [])
                    ]
                else:
                    meta = gmeta.get(it["gid"], {})
                    it["file_size"] = it["file_size"] or meta.get("file_size")
                    it["title_jpn"] = meta.get("title_jpn")
                    it["display_title"] = (
                        resolve_display_title(it["title"] or meta.get("title"), meta.get("title_jpn"))
                        or it["title"] or f"gid {it['gid']}"
                    )
                    it["posted_at"] = _unix_to_iso(meta.get("posted"))
                    it["tags"] = [
                        {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
                        for ns, name in _parse_gdata_tags(meta.get("tags", []))
                    ]
            cover_map = await _remote_cover_data_batch(cloud_pairs, gmeta)
            for it in group_items:
                if it["gallery_id"] is None:
                    it["cover_data"] = cover_map.get(it["gid"])
            missing_posted = [
                (it["gid"], it["token"])
                for it in group_items
                if not it["posted_at"] and it["token"]
            ]
            if missing_posted and app.state.eh_client is not None:
                try:
                    posted_meta = await app.state.eh_client.fetch_gmetadata(missing_posted)
                except Exception as exc:  # noqa: BLE001 - best-effort
                    posted_meta = {}
                    logger.warning(
                        "duplicate posted enrichment failed",
                        extra=log_extra(error=type(exc).__name__),
                    )
                local_write: dict[int, datetime] = {}
                for it in group_items:
                    if it["posted_at"] or it["gid"] not in posted_meta:
                        continue
                    posted = _unix_to_iso(posted_meta[it["gid"]].get("posted"))
                    if not posted:
                        continue
                    it["posted_at"] = posted
                    if it["gallery_id"] is not None:
                        local_write[it["gid"]] = datetime.fromisoformat(posted)
                if local_write:
                    async with _settings_session() as session, session.begin():
                        await FavoritesRepository(session).update_posted_at(local_write)
            ignored_keys = await FavoritesRepository(session).ignored_duplicate_keys()
            groups = [g for g in groups if g["key"] not in ignored_keys]
            groups.sort(key=lambda g: -len(g["items"]))
            duplicates_state["groups"] = groups
            duplicates_state["ignored"] = await FavoritesRepository(session).ignored_duplicates()
            duplicates_state["done"] = len(items)
            duplicates_state["stage"] = "done"
    except Exception as exc:  # noqa: BLE001
        duplicates_state["last_error"] = f"{type(exc).__name__}: {exc}"
        duplicates_state["stage"] = "error"
    finally:
        duplicates_state["running"] = False




class DuplicateIgnoreRequest(BaseModel):
    key: str
    title: str | None = None
    gids: list[int] = Field(default_factory=list)










_FAV_COUNTS_TTL = 300.0
_fav_counts_cache: dict[str, object] = {"ts": 0.0, "counts": {}}
_fav_counts_refreshing = False


async def _refresh_favorite_counts() -> None:
    """Background refresh of the live favorite counts (stale-while-revalidate)."""
    global _fav_counts_refreshing
    if _fav_counts_refreshing or app.state.eh_client is None:
        return
    _fav_counts_refreshing = True
    import time as _time

    try:
        async with asyncio.timeout(60):
            counts = await app.state.eh_client.fetch_favorite_counts()
        _fav_counts_cache["ts"] = _time.time()
        _fav_counts_cache["counts"] = counts
    except Exception as exc:  # noqa: BLE001 - a failed refresh keeps the stale counts
        logger.warning(
            "favorite counts refresh failed", extra=log_extra(error=type(exc).__name__)
        )
    finally:
        _fav_counts_refreshing = False


async def _favorite_counts_cached() -> dict[int, int]:
    """Live per-folder gallery counts, cached for ``_FAV_COUNTS_TTL`` seconds.

    After the TTL expires the stale counts are served immediately while a
    background refresh happens (stale-while-revalidate), so the Favorites page
    never blocks on a slow ExHentai fetch.  Only the very first call ever blocks,
    and even then only briefly (10s timeout).
    """
    import time as _time

    now = _time.time()
    if now - float(_fav_counts_cache["ts"]) < _FAV_COUNTS_TTL:
        return dict(_fav_counts_cache["counts"])  # type: ignore[arg-type]
    if app.state.eh_client is None:
        return {}
    if _fav_counts_cache["counts"]:
        _spawn(_refresh_favorite_counts(), "favorite counts refresh")
        return dict(_fav_counts_cache["counts"])  # type: ignore[arg-type]
    try:
        async with asyncio.timeout(10):
            counts = await app.state.eh_client.fetch_favorite_counts()
        _fav_counts_cache["ts"] = now
        _fav_counts_cache["counts"] = counts
        return counts
    except Exception as exc:  # noqa: BLE001 - degrade gracefully on the first call
        logger.warning(
            "favorite counts fetch failed", extra=log_extra(error=type(exc).__name__)
        )
        return {}


def _estimate_cloud_size(cloud: int, local: int, local_size: int) -> int:
    """Estimate how much syncing the whole folder would take.

    Uses the average size of the galleries we already have locally as a proxy
    for the missing ones; 0 when there is no local sample to average against.
    """
    if cloud <= 0:
        return 0
    if local > 0:
        average = local_size / local
        return int(average * cloud)
    return 0


async def _favorite_size_sync(favcat: int) -> None:
    """Backfill sizes + the metadata cache for one favorite folder.

    Local galleries are seeded into ``gallery_metadata`` straight from the DB
    (no network); the remaining cloud-only gids are fetched with the batched
    gdata API (25 per request) in a bounded loop.  This is what lets a gallery
    scanned onto disk later reuse tags/title/category/posted without a fresh
    ExHentai fetch.  Progress is reported on the Tasks page.
    """
    global _metadata_sync_active
    _metadata_sync_active += 1
    metadata_sync_state["running"] = True
    metadata_sync_state["completed_at"] = None
    if metadata_sync_state.get("started_at") is None:
        metadata_sync_state["started_at"] = datetime.now(UTC).isoformat()
    # Several favcats can be synced concurrently through the same shared state;
    # only the first of the batch resets the counters so progress reflects the
    # current run instead of accumulating across every folder and invocation.
    if _metadata_sync_active == 1:
        metadata_sync_state["total"] = 0
        metadata_sync_state["done"] = 0
        metadata_sync_state["applied"] = 0
    cancelled = False
    try:
        try:
            client = app.state.eh_client
            if client is None:
                return
            async with _settings_session() as session, session.begin():
                seeded = await GalleryRepository(session).seed_metadata_from_galleries(favcat)
            total_cached = seeded
            metadata_sync_state["stage"] = "sync"
            for _round in range(60):
                if _cancelled("metadata"):
                    cancelled = True
                    break
                async with _settings_session() as session:
                    pending = await FavoritesRepository(session).pending_size_gids(favcat, 500)
                    cold = await GalleryRepository(session).cold_metadata_gids(favcat, 500)
                seen: set[int] = set()
                pairs: list[tuple[int, str]] = []
                for gid, token in pending + cold:
                    if gid not in seen:
                        seen.add(gid)
                        pairs.append((gid, token))
                if not pairs:
                    break
                try:
                    metadata = await client.fetch_gmetadata(pairs)
                except Exception as exc:  # noqa: BLE001 - stop the loop, retry next check
                    logger.warning(
                        "favorite metadata sync round failed",
                        extra=log_extra(favcat=favcat, error=type(exc).__name__),
                    )
                    break
                sizes = {
                    gid: size
                    for gid, meta in metadata.items()
                    if (size := meta.get("file_size"))
                }
                async with _settings_session() as session, session.begin():
                    for gid, size in sizes.items():
                        await FavoritesRepository(session).set_file_size(favcat, gid, size)
                    await GalleryRepository(session).upsert_metadata(
                        [{"gid": gid, **meta} for gid, meta in metadata.items()]
                    )
                # Warm the folder's cover files on disk while the fresh gdata
                # response still carries the thumb URLs (a favorites check is
                # meant to pull covers, tags and sizes together).  Already-cached
                # files are skipped; failures are best-effort — the lazy items
                # endpoint still fetches stragglers from disk-first.
                try:
                    await _remote_cover_data_batch(pairs, metadata)
                except Exception as exc:  # noqa: BLE001 - covers are best-effort
                    logger.warning(
                        "favorite cover download failed",
                        extra=log_extra(favcat=favcat, error=type(exc).__name__),
                    )
                total_cached += len(metadata)
                metadata_sync_state["total"] = int(metadata_sync_state["total"]) + len(pairs)
                metadata_sync_state["done"] = int(metadata_sync_state["done"]) + len(metadata)
                if len(cold) < 500:
                    break
            if total_cached:
                logger.info(
                    "favorite metadata synced", extra=log_extra(favcat=favcat, cached=total_cached)
                )
            # Heal missing covers: walk the folder's stored thumb URLs (captured
            # from the favorites listing during the check) and download the ones
            # missing on disk — no gdata round-trip needed.  Already-warm files
            # are skipped, so a folder check really pulls covers (the intended
            # design) instead of leaving them to the lazy browsing endpoint.
            metadata_sync_state["stage"] = "covers"
            try:
                async with _settings_session() as session:
                    folder_items = await FavoritesRepository(session).all_gids_for_favcat(favcat)
                cache_dir = _remote_cover_cache_dir()
                coverless = [
                    (gid, token, thumb)
                    for gid, token, thumb in folder_items
                    if not (cache_dir / f"{gid}.img").is_file()
                ]
                for start in range(0, len(coverless), 500):
                    if _cancelled("metadata"):
                        cancelled = True
                        break
                    chunk = coverless[start : start + 500]
                    meta = {
                        gid: {"thumb": thumb}
                        for gid, _token, thumb in chunk
                        if thumb
                    }
                    if meta:
                        await _remote_cover_data_batch(
                            [(gid, token) for gid, token, _thumb in chunk], meta, quiet=True
                        )
                        metadata_sync_state["done"] = (
                            int(metadata_sync_state["done"]) + len(meta)
                        )
                    # Gentle pacing: a full folder of missing covers is a one-time
                    # burst and must not trip anti-abuse on the thumb CDN.
                    await asyncio.sleep(1)
                if coverless:
                    logger.info(
                        "favorite covers healed",
                        extra=log_extra(favcat=favcat, healed=len(coverless)),
                    )
            except Exception as exc:  # noqa: BLE001 - covers are best-effort
                logger.warning(
                    "favorite cover heal failed",
                    extra=log_extra(favcat=favcat, error=type(exc).__name__),
                )
            # Apply the fresh metadata (tags, category, title, posted, sizes) to the
            # on-disk galleries of this folder, so local tags stay in sync without
            # any per-gallery ExHentai fetch.  Skipped automatically when the cache
            # is unchanged since the last apply.
            applied = 0
            metadata_sync_state["stage"] = "apply"
            for _apply_round in range(100):
                if _cancelled("metadata"):
                    cancelled = True
                    break
                async with _settings_session() as session, session.begin():
                    applied_round = await GalleryRepository(session).apply_metadata_to_galleries(
                        favcat, 200
                    )
                if not applied_round:
                    break
                applied += applied_round
                metadata_sync_state["applied"] = int(metadata_sync_state["applied"]) + applied_round
            if applied:
                logger.info(
                    "favorite metadata applied", extra=log_extra(favcat=favcat, applied=applied)
                )
        except Exception as exc:  # noqa: BLE001 - background task must not crash
            metadata_sync_state["last_error"] = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "favorite metadata sync failed",
                extra=log_extra(favcat=favcat, error=type(exc).__name__),
            )
            cancelled = True
    finally:
        _metadata_sync_active -= 1
        if _metadata_sync_active <= 0:
            metadata_sync_state["running"] = False
            metadata_sync_state["completed_at"] = datetime.now(UTC).isoformat()
            _record_task(
                "metadata",
                metadata_sync_state.get("started_at"),
                metadata_sync_state["completed_at"],
                "cancelled"
                if cancelled
                else ("failed" if metadata_sync_state.get("last_error") else "success"),
                reason=(
                    "cancelled"
                    if cancelled
                    else str(metadata_sync_state.get("last_error") or "")
                ),
                done=int(metadata_sync_state.get("done") or 0),
                total=int(metadata_sync_state.get("total") or 0),
            )
            metadata_sync_state["stage"] = None
            metadata_sync_state["started_at"] = None
            _clear_cancelled("metadata")






async def _run_favorites_check(
    favcat: int, service: FavoritesService, *, scheduled: bool = False
) -> None:
    entry: dict[str, object] = {
        "running": True,
        "started": datetime.now(UTC).isoformat(),
        "error": None,
        "done": 0,
        "total": 0,
    }
    categories = favorites_check_state["categories"]
    assert isinstance(categories, dict)
    categories[str(favcat)] = entry
    favorites_check_state["running"] = True
    if favorites_check_state.get("started_at") is None:
        favorites_check_state["started_at"] = datetime.now(UTC).isoformat()
        favorites_check_state["history_recorded"] = False
    try:
        try:
            counts = await _favorite_counts_cached()
            entry["total"] = counts.get(favcat, 0)
        except Exception as exc:  # noqa: BLE001 - live count is best-effort
            logger.warning(
                "could not fetch live count for check progress",
                extra=log_extra(favcat=favcat, error=type(exc).__name__),
            )

        async with _settings_session() as session:
            category = await FavoritesRepository(session).category(favcat)
        # Scheduled polls skip the full re-list when the folder count on the
        # cloud matches the galleries we already recorded from a previous
        # successful check.  A big folder (several thousand items) otherwise
        # re-walks every favorites page every poll for no new data.  Manual
        # "check now" always does a full pass.
        live_count = int(entry.get("total") or 0)
        if scheduled and category is not None and category.last_success_at is not None:
            try:
                async with _settings_session() as session:
                    known = await FavoritesRepository(session).count_known_gids(favcat)
                if live_count > 0 and known == live_count:
                    entry["done"] = entry["total"] = live_count
                    entry["skipped"] = True
                    async with _settings_session() as session, session.begin():
                        await FavoritesRepository(session).checked(favcat, True)
                    logger.info(
                        "favorites check skipped (cloud count unchanged)",
                        extra=log_extra(favcat=favcat, cloud=live_count, known=known),
                    )
                    return
            except Exception as exc:  # noqa: BLE001 - fall through to a full check
                logger.warning(
                    "favorites skip heuristic failed",
                    extra=log_extra(favcat=favcat, error=type(exc).__name__),
                )

        def _progress(done: int) -> None:
            entry["done"] = done

        # A disabled folder is check-only: record entries but never download. It
        # only starts downloading once the user enables the folder.
        if category is not None and not category.enabled:
            await service.check_category(favcat, mode="monitor_only", progress=_progress)
        else:
            await service.check_category(
                favcat,
                mode=category.mode if category else "incremental",
                progress=_progress,
            )
        _spawn(_favorite_size_sync(favcat), f"favorite size sync {favcat}")
    except Exception as exc:  # noqa: BLE001 - record and surface in the UI
        entry["error"] = f"{type(exc).__name__}: {exc}"
        favorites_check_state["last_error"] = entry["error"]
        logger.warning(
            "favorites check failed", extra=log_extra(favcat=favcat, error=type(exc).__name__)
        )
    finally:
        entry["running"] = False
        favorites_check_state["running"] = any(
            item.get("running") for item in categories.values()
        )
        if (
            not favorites_check_state["running"]
            and favorites_check_state.get("started_at")
            and not favorites_check_state["history_recorded"]
        ):
            favorites_check_state["history_recorded"] = True
            favorites_check_state["completed_at"] = datetime.now(UTC).isoformat()
            _record_task(
                "favcheck",
                favorites_check_state.get("started_at"),
                favorites_check_state["completed_at"],
                "failed" if favorites_check_state.get("last_error") else "success",
                reason=str(favorites_check_state.get("last_error") or ""),
                done=sum(
                    int(item.get("done") or 0)
                    for item in categories.values()
                    if isinstance(item, dict)
                ),
                total=sum(
                    int(item.get("total") or 0)
                    for item in categories.values()
                    if isinstance(item, dict)
                ),
            )
            favorites_check_state["started_at"] = None


async def _favorites_poll_loop() -> None:
    """Poll configured favorite categories without delaying application startup."""
    while True:
        await asyncio.sleep(30)
        if not _settings().download_favorites_enabled:
            logger.debug("favorites polling skipped: download favorites is disabled")
            await asyncio.sleep(max(1, _settings().favorites_poll_interval_minutes) * 60)
            continue
        if not _settings().exhentai_cookies:
            logger.debug("favorites polling skipped: ExHentai cookies are not configured")
            await asyncio.sleep(max(1, _settings().favorites_poll_interval_minutes) * 60)
            continue
        service = app.state.favorites_service
        if service is None:
            continue
        for favcat in _settings().favorites_categories:
            try:
                async with _settings_session() as session:
                    category = await FavoritesRepository(session).category(favcat)
                if category is not None and not category.enabled:
                    continue
                if category is not None and category.last_checked_at is not None:
                    elapsed = (datetime.now(UTC) - category.last_checked_at).total_seconds()
                    if elapsed < max(60, category.poll_interval_seconds):
                        continue
                _spawn(
                    _run_favorites_check(favcat, service, scheduled=True),
                    "scheduled favorites check",
                )
                logger.info("scheduled favorites check", extra=log_extra(favcat=favcat))
            except Exception as exc:  # noqa: BLE001 - one category must not stop the scheduler
                logger.error(
                    "scheduled favorites check failed",
                    extra=log_extra(favcat=favcat, error=type(exc).__name__),
                )



async def _gallery(identifier: int) -> tuple[Gallery, list[GalleryPage]]:
    try:
        async with _settings_session() as session:
            # Two-pass lookup: a gallery whose ``id`` equals another gallery's
            # ``gid`` would make ``or_`` + ``scalar_one_or_none`` raise
            # MultipleResultsFound.  Query by primary key first, fall back to
            # gid only when that misses.
            row = await session.scalar(select(Gallery).where(Gallery.id == identifier))
            if row is None:
                row = await session.scalar(select(Gallery).where(Gallery.gid == identifier))
            if row is None:
                raise HTTPException(status_code=404, detail="Gallery not found")
            pages = (
                await session.scalars(
                    select(GalleryPage)
                    .where(GalleryPage.gallery_id == row.id)
                    .order_by(GalleryPage.page_index)
                )
            ).all()
            return row, list(pages)
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc


async def _gallery_tags(gallery_id: int) -> list[tuple[str, str]]:
    try:
        async with _settings_session() as session:
            rows = await session.execute(
                select(Tag.namespace, Tag.name)
                .join(GalleryTag, GalleryTag.tag_id == Tag.id)
                .where(GalleryTag.gallery_id == gallery_id)
                .order_by(Tag.namespace, Tag.name)
            )
            return [(namespace, name) for namespace, name in rows]
    except Exception as exc:
        raise _db_error(exc) from exc


def _meta(row: Gallery, pages: list[GalleryPage]) -> GalleryMeta:
    return GalleryMeta(
        title=row.title,
        path=Path(row.storage_path),
        storage_type=row.storage_type,
        pages=[
            PageInfo(
                p.page_index,
                p.member_name,
                p.media_type,
                (p.manifest or {}).get("size"),
                (p.manifest or {}).get("mtime_ns"),
            )
            for p in pages
        ],
        gid=row.gid,
        token=row.token,
        storage_signature=row.storage_signature,
    )





class ProgressRequest(BaseModel):
    current_page: int = Field(ge=0)
    total_pages: int | None = Field(default=None, ge=0)






class BulkDeleteRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)
    delete_files: bool = False


class FilteredDeleteRequest(BaseModel):
    """Server-side "delete everything matching this filter" request.

    The SPA used to resolve the current library filter into a full id list on
    the client and POST it to ``delete-bulk``.  For big libraries that list can
    be tens of thousands of ids, blowing past asyncpg's ~32767 param limit when
    the backend issues ``Gallery.id.in_(ids)``.  This endpoint pages the filter
    query itself and deletes in 500-row batches, so the client only sends the
    filter, never the ids.
    """

    q: str = ""
    category: str | None = None
    tags: str | None = None
    tag_mode: str = "or"
    tag_match: str = "exact"
    delete_files: bool = False


def _in_scan_roots(path: Path) -> bool:
    """True when ``path`` (resolved) sits under one of the configured scan roots."""
    try:
        resolved = path.resolve()
    except (ValueError, TypeError, OSError):
        return False
    return any(resolved.is_relative_to(root) for root in _scan_roots())


def _delete_local_copy(path: Path) -> bool:
    """Delete one on-disk copy (directory or single file). Returns success."""
    try:
        if path.is_dir():
            import shutil as _shutil

            _shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        return True
    except OSError:
        logger.warning("gallery file removal failed", extra={"path": str(path)})
        return False


async def delete_galleries_local(
    session,
    galleries: list[Gallery],
    *,
    delete_files: bool,
    delete_all_copies: bool,
) -> list[dict]:
    """Delete galleries (DB rows + optional on-disk copies) via a shared path.

    ``delete_files`` controls whether on-disk files are removed.  ``delete_all_copies``
    extends deletion to every physical copy of a gid recorded in ``duplicate_records``
    (used by the favorites dedup page, where one gid may live under several roots).

    A gallery row is only deleted when every target path was removed successfully
    (or ``delete_files`` is False); a partial failure keeps the row so a later
    scan cannot resurrect a half-deleted gallery as if it were fresh.  Returned per
    gallery: ``{gallery_id, gid, db_removed, deleted_paths, failed_paths}``.
    """
    results: list[dict] = []
    for gallery in galleries:
        gid = gallery.gid
        targets = [Path(gallery.storage_path)] if gallery.storage_path else []
        if delete_all_copies and gid is not None:
            copies = await GalleryRepository(session).duplicate_copies_for_gid(gid)
            for copy in copies:
                p = Path(str(copy.get("path") or ""))
                if p not in targets:
                    targets.append(p)
        deleted_paths: list[str] = []
        failed_paths: list[str] = []
        if delete_files:
            for target in targets:
                if not _in_scan_roots(target):
                    continue
                if _delete_local_copy(target):
                    deleted_paths.append(str(target))
                else:
                    failed_paths.append(str(target))
        if not delete_files or not failed_paths:
            await session.delete(gallery)
            if delete_all_copies and gid is not None and not failed_paths:
                await GalleryRepository(session).delete_duplicate(gid)
            db_removed = True
        else:
            db_removed = False
        results.append(
            {
                "gallery_id": gallery.id,
                "gid": gid,
                "db_removed": db_removed,
                "deleted_paths": deleted_paths,
                "failed_paths": failed_paths,
            }
        )
    await session.flush()
    return results






def _page_media_type(ext: str) -> str:
    """Map a page file extension to a standards-compliant media type."""
    return {"jpg": "image/jpeg", "jpe": "image/jpeg", "jpeg": "image/jpeg"}.get(
        (ext or "").lower(), f"image/{ext}"
    )


_PAGE_STREAM_CHUNK = 256 * 1024


def _closing_stream(stream: BinaryIO) -> Iterator[bytes]:
    """Yield a sync page stream in 256KB chunks, closing the file when exhausted.

    StreamingResponse iterates sync iterators in a threadpool round-trip per
    chunk. A plain ``yield from stream`` iterates in the file's 8KB buffer size,
    which caps large-page throughput near ~1MB/s (painful for big animated WebP
    pages). Reading 256KB per chunk removes the per-chunk overhead. The finally
    block closes a raw file object so every served page leaves no descriptor
    behind.
    """
    try:
        while True:
            chunk = stream.read(_PAGE_STREAM_CHUNK)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _thumb_service() -> ThumbnailService:
    global thumb_service
    if thumb_service is None:
        thumb_service = ThumbnailService(_settings().thumbnail_cache_dir)
    return thumb_service


def _remote_cover_cache_dir() -> Path:
    return Path(_settings().thumbnail_cache_dir).parent / "remote-covers"


def _img_data_uri(data: bytes) -> str:
    media_type = _image_content_type(data)
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _unix_to_iso(value: object) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


async def _favorites_metadata(pairs: list[tuple[int, str]]) -> dict[int, dict[str, object]]:
    """DB-first metadata for cloud favorite pairs, in the gdata response shape.

    A favorites check warms the ``gallery_metadata`` cache for the whole folder,
    so browsing/managing favorites must read the database, not ExHentai — only
    gids that have never been cached are fetched from ExHentai. Keeps the
    thumbnails on disk (already downloaded during the check) working because the
    cover loader checks the filesystem cache first.
    """
    if not pairs:
        return {}
    gids = [gid for gid, _ in pairs]
    try:
        async with _settings_session() as session:
            cached = await GalleryRepository(session).metadata_map(gids)
    except Exception as exc:  # noqa: BLE001 - DB down: fall through to cloud
        logger.warning(
            "favorites metadata cache read failed",
            extra=log_extra(error=type(exc).__name__),
        )
        cached = {}
    merged: dict[int, dict[str, object]] = {}
    for gid, meta in cached.items():
        # metadata_map returns tags as ``{"namespace": ..., "name": ...}``
        # dicts; normalise them into the gdata ``namespace:name`` strings the
        # caller re-parses (previously the dict keys were unpacked as the tag
        # values, rendering every tag as ``namespace:name``).
        gtags = _tags_to_gdata_strings(meta.get("tags"))
        posted = meta.get("posted_at")
        merged[int(gid)] = {
            "token": meta.get("token") or "",
            "thumb": "",
            "title": meta.get("title") or "",
            "title_jpn": meta.get("title_jpn"),
            "category": meta.get("category"),
            "file_count": meta.get("file_count") or 0,
            "file_size": meta.get("file_size"),
            "tags": gtags,
            "posted": int(posted.timestamp()) if posted else 0,
            "expunged": bool(meta.get("expunged")),
            "uploader": meta.get("uploader"),
            "rating": float(meta.get("rating") or 0),
        }
    missing = [(gid, token) for gid, token in pairs if gid not in merged]
    if missing and app.state.eh_client is not None:
        try:
            gmeta = await app.state.eh_client.fetch_gmetadata(missing)
            merged.update({int(gid): dict(m) for gid, m in gmeta.items()})
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.warning(
                "favorites gdata fetch failed",
                extra=log_extra(error=type(exc).__name__),
            )
    return merged


def _parse_gdata_tags(raw_tags: list[str]) -> list[tuple[str | None, str]]:
    out = []
    for value in raw_tags:
        if not value:
            continue
        if ":" in value:
            namespace, name = value.split(":", 1)
        else:
            namespace, name = None, value
        out.append((namespace or None, name.strip()))
    return out


def _tags_to_gdata_strings(raw_tags: list[object]) -> list[str]:
    """Normalize stored metadata tags into gdata ``namespace:name`` strings.

    ``gallery_metadata`` stores tags as ``[["ns", "name"], ...]`` pairs and
    ``metadata_map`` surfaces them as ``{"namespace":..., "name":...}`` dicts;
    either shape is accepted.  The result feeds ``_parse_gdata_tags`` which
    re-splits them, so the round trip never yields the literal key names.
    """
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


async def _remote_cover_data_batch(
    pairs: list[tuple[int, str]],
    metadata: dict[int, dict[str, object]],
    *,
    quiet: bool = False,
) -> dict[int, str]:
    """Download (and cache) ExHentai cover thumbnails, returning base64 data URIs.

    One gdata metadata fetch already resolved the thumb URLs in bulk; this only
    downloads the small images, concurrently and cached under
    ``/gv-cache/remote-covers/{gid}.img``.  ``quiet`` silences the per-cover
    failure log, used when warming a whole folder (thousands of covers).
    """
    if not pairs:
        return {}
    cache_dir = _remote_cover_cache_dir()
    client = app.state.eh_client
    if client is None:
        return {}
    semaphore = asyncio.Semaphore(8)

    async def fetch_one(gid: int, thumb_url: str) -> str | None:
        path = cache_dir / f"{gid}.img"
        if path.is_file():
            return _img_data_uri(path.read_bytes())
        if not thumb_url:
            return None
        async with semaphore:
            try:
                response = await client.client.get(
                    thumb_url,
                    headers={"Referer": _settings().exhentai_base_url.rstrip("/") + "/"},
                )
                if response.status_code != 200 or len(response.content) < 200:
                    return None
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(response.content)
                tmp.replace(path)
                return _img_data_uri(response.content)
            except Exception as exc:  # noqa: BLE001 - one cover must not fail the list
                if not quiet:
                    logger.warning(
                        "remote cover download failed",
                        extra=log_extra(gid=gid, error=type(exc).__name__),
                )
                return None

    results = await asyncio.gather(
        *(
            fetch_one(gid, str((metadata.get(gid) or {}).get("thumb", "") or ""))
            for gid, _ in pairs
        )
    )
    return {gid: data for (gid, _), data in zip(pairs, results) if data}


def _image_content_type(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF89a", b"GIF87a"):
        return "image/gif"
    return "application/octet-stream"


async def _thumbnail_gallery(gallery_id: int) -> tuple[int, int]:
    """Generate (or refresh) cached thumbnails for one gallery, page by page.

    Returns ``(generated_pages, failed_pages)`` so the worker can count a
    gallery as succeeded/failed once (progress is per gallery, matching total).
    """
    generated = 0
    failed_pages = 0
    async with _settings_session() as session:
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
                PageInfo(page.page_index, page.member_name, page.media_type),
            )
            data = await run_in_threadpool(stream.read)
            await run_in_threadpool(
                service.get_or_create, gallery_id, page.page_index, data
            )
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


async def _seed_thumbnails() -> None:
    """Queue every gallery missing its cover thumbnail for background generation.

    ``total`` reflects the remaining work (galleries still missing a cover), so
    a container restart continues the remaining work instead of looking like it
    restarted from zero — cached thumbnails are never regenerated.
    """
    async with _settings_session() as session:
        rows = await session.execute(
            select(Gallery.id, Gallery.page_count).where(
                Gallery.page_count.is_not(None), Gallery.expunged.is_(False)
            )
        )
        pairs = [(int(row[0]), int(row[1])) for row in rows if row[1]]
    service = _thumb_service()
    missing: list[int] = []
    missing_total = 0
    for gallery_id, page_count in pairs:
        if service.cached(gallery_id, 0) is not None:
            continue
        missing_total += 1
        missing.append(gallery_id)
    added = 0
    for start in range(0, len(missing), 500):
        async with _settings_session() as session, session.begin():
            added += await BackgroundJobsRepository(session).enqueue_many(
                JOB_THUMB, missing[start : start + 500]
            )
    thumb_state["total"] = missing_total
    thumb_state["queued"] = await _jobs_count(JOB_THUMB)
    if added:
        thumb_state["running"] = True
        thumb_state["completed_at"] = None
    logger.info(
        "thumbnail seeding complete", extra=log_extra(queued=added, pending=missing_total)
    )


async def _thumbnail_worker_loop() -> None:
    concurrency = 4
    thumb_state["running"] = True
    last_activity = [_time.monotonic()]
    # Reopen jobs whose claiming worker died before completing them.
    try:
        async with _settings_session() as session, session.begin():
            await BackgroundJobsRepository(session).mark_stale()
    except Exception as exc:  # noqa: BLE001 - recovery must not kill the worker
        logger.warning(
            "thumbnail stale-recovery failed", extra=log_extra(error=type(exc).__name__)
        )

    async def _worker() -> None:
        while True:
            if _cancelled("thumbs"):
                break
            claimed = await _claim_jobs(JOB_THUMB, 1)
            if not claimed:
                # Queue drained: reflect idle once it has been empty for a few
                # seconds (mirrors the old wait_for(5s) timeout) so the
                # task-progress UI hides, but keep the finished progress visible.
                if (
                    _time.monotonic() - last_activity[0] >= _THUMB_IDLE_SECONDS
                    and thumb_state["running"]
                ):
                    thumb_state["completed_at"] = datetime.now(UTC).isoformat()
                    thumb_state["queued"] = await _jobs_count(JOB_THUMB)
                    thumb_state["running"] = False
                    if (
                        thumb_state.get("started_at")
                        and not thumb_state["history_recorded"]
                    ):
                        thumb_state["history_recorded"] = True
                        _record_task(
                            "thumbs",
                            thumb_state.get("started_at"),
                            thumb_state["completed_at"],
                            "success",
                            reason=(
                                f"ok {thumb_state.get('succeeded', 0)} "
                                f"/ fail {thumb_state.get('failed', 0)}"
                            ),
                            done=int(thumb_state.get("succeeded") or 0)
                            + int(thumb_state.get("failed") or 0),
                            total=int(thumb_state.get("total") or 0),
                        )
                await asyncio.sleep(_THUMB_POLL_INTERVAL)
                continue
            gallery_id = claimed[0][0]
            last_activity[0] = _time.monotonic()
            if not thumb_state["running"] or not thumb_state.get("started_at"):
                thumb_state["running"] = True
                thumb_state["completed_at"] = None
                thumb_state["started_at"] = datetime.now(UTC).isoformat()
                thumb_state["history_recorded"] = False
            try:
                _generated, failed_pages = await _thumbnail_gallery(gallery_id)
                if failed_pages == 0:
                    thumb_state["succeeded"] += 1
                else:
                    thumb_state["failed"] += 1
                    thumb_state["last_error"] = f"{failed_pages} pages failed"
            except Exception as exc:  # noqa: BLE001 - one gallery must not stop the worker
                thumb_state["failed"] += 1
                thumb_state["last_error"] = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "thumbnail generation failed",
                    extra=log_extra(gallery_id=gallery_id, error=type(exc).__name__),
                )
            thumb_state["processed"] += 1
            await _complete_job(JOB_THUMB, gallery_id)

    workers = [asyncio.create_task(_worker()) for _ in range(concurrency)]
    try:
        await asyncio.gather(*workers)
    finally:
        if _cancelled("thumbs"):
            thumb_state["running"] = False
            thumb_state["completed_at"] = datetime.now(UTC).isoformat()
            if not thumb_state["history_recorded"]:
                thumb_state["history_recorded"] = True
                _record_task(
                    "thumbs",
                    thumb_state.get("started_at"),
                    thumb_state["completed_at"],
                    "cancelled",
                    reason="cancelled",
                    done=int(thumb_state.get("succeeded") or 0)
                    + int(thumb_state.get("failed") or 0),
                    total=int(thumb_state.get("total") or 0),
                )
            _clear_cancelled("thumbs")






_tag_facets_cache: dict[str, object] = {"ts": 0.0, "facets": []}
_TAG_FACETS_TTL = 120.0


async def _tag_facets_cached() -> list[tuple[str, int]]:
    """Per-namespace tag counts, cached (they change slowly with scans)."""
    import time as _time

    now = _time.time()
    if now - float(_tag_facets_cache["ts"]) < _TAG_FACETS_TTL:
        return list(_tag_facets_cache["facets"])  # type: ignore[arg-type]
    async with _settings_session() as session:
        facets = await GalleryRepository(session).tag_facets()
    _tag_facets_cache["ts"] = now
    _tag_facets_cache["facets"] = facets
    return facets






@app.get("/api/auth/session")
async def auth_session() -> dict[str, object]:
    return {
        "authenticated": True,
        "auth_required": _settings().auth_required,
        "must_change_password": _must_change_password(),
    }


@app.get("/api/onboarding/status")
async def onboarding_status() -> dict[str, object]:
    """Setup progress used by the first-run wizard (password, ExHentai, library)."""
    settings = _settings()
    password_default = settings.auth_required and not (
        settings.auth_password_hash or settings.auth_password
    )
    exhentai_configured = bool(settings.exhentai_cookies)
    library_count = 0
    try:
        async with _settings_session() as session:
            library_count = int(
                await session.scalar(select(func.count()).select_from(Gallery)) or 0
            )
    except Exception as exc:  # noqa: BLE001 - DB down: fall back to a 0 count
        logger.warning("onboarding status could not read library count", extra={"error": str(exc)})
    return {
        "password_default": password_default,
        "exhentai_configured": exhentai_configured,
        "library_count": library_count,
    }


class ChangePasswordRequest(BaseModel):
    current: str = ""
    new: str = Field(min_length=1, max_length=256)


@app.post("/api/auth/change-password", status_code=204)
async def change_password(body: ChangePasswordRequest) -> None:
    effective = _password_effective()
    using_default = effective is None
    current_valid = (
        using_default and body.current == DEFAULT_PASSWORD
    ) or verify_login_password(body.current, effective)
    if not current_valid:
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    if body.new == DEFAULT_PASSWORD and using_default:
        raise HTTPException(status_code=422, detail="New password cannot be the default")
    new_hash = hash_password(body.new)
    # Rotate auth_secret so every previously issued session cookie is revoked.
    # The secret must be applied to the RUNNING process (not just persisted):
    # ``_apply_persisted_settings`` only re-applies the password hash, so
    # without the model_copy below revocation would silently wait for the next
    # restart while the DB already held the new secret.
    import secrets as _secrets

    new_secret = _secrets.token_urlsafe(32)
    stored = {"auth_password_hash": new_hash, "auth_secret": new_secret}
    if encryption_enabled():
        stored = {k: encrypt(v) for k, v in stored.items()}
    try:
        async with _settings_session() as session, session.begin():
            await SettingsRepository(session).save_extra(stored)
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    app.state.settings = app.state.settings.model_copy(
        update={"auth_secret": new_secret, "auth_password_hash": new_hash}
    )
    # Hand the current user a fresh cookie signed with the new secret so their
    # own password change does not log them out while everyone else's old
    # sessions are revoked immediately.
    response = Response(status_code=204)
    response.set_cookie(
        _settings().auth_cookie_name,
        create_session(new_secret, _settings().auth_session_ttl),
        httponly=True,
        samesite="lax",
        secure=_settings().auth_cookie_secure,
        max_age=_settings().auth_session_ttl,
    )
    logger.info("account password changed")
    return response



# Routers are wired at the very end so this module is fully initialized before
# they import it (their handlers annotate parameters with e.g.
# main.DownloadRequest, which must already exist).
from .routers import core, downloads, duplicates, favorites, galleries, settings, tags, tasks

app.include_router(tasks.router)
app.include_router(duplicates.router)
app.include_router(downloads.router)
app.include_router(settings.router)
app.include_router(galleries.router)
app.include_router(favorites.router)
app.include_router(tags.router)
app.include_router(core.router)
