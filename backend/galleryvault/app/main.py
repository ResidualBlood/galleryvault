import asyncio
import contextlib
import hmac
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from urllib.parse import parse_qs

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
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
    DownloadRepository,
    FavoritesRepository,
    GalleryRepository,
    SettingsRepository,
)
from ..db.session import create_database
from ..logging import configure_logging, log_extra
from ..scanners import registry
from ..scanners.base import CATEGORIES, GalleryMeta, PageInfo
from ..services.downloader import DownloadCancelledError, Downloader, DownloadTask
from ..services.eh_client import EhClient, EhClientError, GalleryGoneError, parse_gallery_url
from ..services.favorites import FavoritesService
from ..services.ingest import GalleryIngestService
from ..services.library import LibraryService
from ..services.tag_sync import (
    GalleryGidMissing,
    GalleryNotFound,
    GalleryTokenMissing,
    TagSyncService,
)
from ..services.tag_translation import (
    load_translations,
    merge_translation_data,
    translated_tag,
    translation_entry_count,
)
from ..services.telegram import TelegramNotifier
from ..services.telegram_bot import TelegramBotService
from ..services.thumbnails import JPEG_MIME, ThumbnailError, ThumbnailService

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
scan_state: dict[str, object] = {"running": False, "last": None}
scan_lock = asyncio.Lock()
download_worker_task = None
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
    "category_refreshed": 0,
    "category_refresh_running": False,
}
tag_sync_queue: asyncio.Queue[int] = asyncio.Queue()
tag_sync_queued: set[int] = set()
tag_sync_attempts: dict[int, int] = {}
tag_sync_worker_task = None
translation_update_task = None
_download_cancelled: set[int] = set()
translation_state: dict[str, object] = {
    "running": False,
    "last": None,
    "last_error": None,
    "entries": 0,
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
}
thumb_queue: asyncio.Queue[int] = asyncio.Queue()
thumb_queued: set[int] = set()
thumb_worker_task = None
thumb_service: ThumbnailService | None = None

# Built-in default password used when no auth hash is configured anywhere. The
# SPA forces a password change once you log in with it.  Documented in the
# frontend README.
DEFAULT_PASSWORD = "p1a2s3s4"


def _settings() -> Settings:
    return app.state.settings


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


def display_title(gallery: object) -> str:
    """Resolve the gallery title shown in the UI from the configured preference.

    Mirrors Ehviewer's ``getSuitableTitle``: Japanese by default, falling back
    to the romaji/English title, then to the directory name with any leading
    gallery id stripped.
    """
    mode = (_settings().title_display or "japanese").lower()
    title = getattr(gallery, "title", None) or ""
    title_jpn = getattr(gallery, "title_jpn", None) or ""
    storage_path = getattr(gallery, "storage_path", "") or ""
    directory = Path(storage_path).name if storage_path else ""
    if mode == "english":
        source = title or title_jpn or directory
    elif mode == "directory":
        source = directory or title_jpn or title
    else:
        source = title_jpn or title or directory
    if not source:
        source = title or title_jpn or directory or str(getattr(gallery, "gid", "") or "")
    stripped = _LEADING_NUMBER.sub("", source).lstrip("-").strip()
    return stripped or source or str(getattr(gallery, "gid", "") or "")


def _scan_roots() -> list[str]:
    roots = list(_settings().library_roots)
    if _settings().download_root not in roots:
        roots.append(_settings().download_root)
    return normalize_library_roots(roots)


@app.middleware("http")
async def authentication(request: Request, call_next):
    path = request.url.path
    if path in {"/healthz", "/login", "/logout"}:
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


async def _runtime_row() -> dict:
    """Read the DB row holding auth secrets (auth_secret, auth_password_hash)."""
    from ..db.models import AppConfig as _AppConfig

    async with _settings_session() as session:
        row = await session.get(_AppConfig, "runtime_auth")
        return dict(row.value) if row else {}


async def _apply_persisted_settings() -> None:
    """Reload user settings + runtime secrets from the DB into app.state.

    The database is the single source of truth: user-editable settings live in
    ``app_config.user_settings`` and secrets in ``app_config.runtime_auth``.
    """
    try:
        async with _settings_session() as session:
            persisted = await SettingsRepository(session).get()
        runtime = await _runtime_row()
        updates: dict[str, object] = {**persisted}
        _update_runtime_settings(updates)
        # Secrets are never part of the editable settings payload; apply the
        # password hash directly so a change takes effect without a restart.
        if runtime.get("auth_password_hash"):
            app.state.settings = app.state.settings.model_copy(
                update={"auth_password_hash": runtime["auth_password_hash"]}
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
        async with _settings_session() as session, session.begin():
            row = await session.get(_AppConfig, "runtime_auth")
            if row is None:
                session.add(_AppConfig(key="runtime_auth", value=merged))
            else:
                row.value = merged
    # Apply the persisted secret (and any env-provided hash) to runtime settings.
    final = await _runtime_row()
    opts: dict[str, object] = {"auth_secret": final.get("auth_secret")}
    if final.get("auth_password_hash"):
        opts["auth_password_hash"] = final["auth_password_hash"]
    app.state.settings = app.state.settings.model_copy(update=opts)


async def _auth_runtime_hash() -> str | None:
    runtime = await _runtime_row()
    return runtime.get("auth_password_hash")


@app.on_event("startup")
async def startup() -> None:
    try:
        async with _settings_session() as session:
            persisted = await SettingsRepository(session).get()
        _update_runtime_settings(persisted)
    except Exception:  # noqa: BLE001 - startup must remain usable when DB is unavailable
        logger.warning("user settings could not be loaded at startup")
    # auth_secret lives in the DB so sessions survive restarts; on the very first
    # boot it is generated here and the env-provided password hash (if any) is
    # imported once.  Every subsequent boot reads both from the DB.
    try:
        await _bootstrap_auth()
    except Exception:  # noqa: BLE001
        logger.warning("auth bootstrap failed; using temporary credentials")
    client = EhClient(_settings())
    app.state.eh_client = client
    app.state.downloader = Downloader(
        client, _settings().download_root, concurrency=_settings().download_concurrency
    )
    app.state.telegram = TelegramNotifier(_settings())
    _start_telegram_bot()
    app.state.favorites_service = FavoritesService(
        client, _FavoritesRepositoryProxy(), _FavoriteDownloadQueue(), app.state.telegram
    )
    app.state.favorite_poll_task = asyncio.create_task(_favorites_poll_loop())
    global download_worker_task
    download_worker_task = asyncio.create_task(_download_worker_loop())
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
    load_translations()
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
    if app.state.telegram is not None:
        await app.state.telegram.aclose()
    if app.state.eh_client is not None:
        await app.state.eh_client.aclose()
    await app.state.engine.dispose()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/login")
async def login(request: Request):
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


async def _run_scan() -> None:
    async with scan_lock:
        persisted = 0
        scanned = 0
        success = 0
        errors = 0
        scan_state["running"] = True
        scan_state["scanned"] = 0
        scan_state["persisted"] = 0
        scan_state["success"] = 0
        scan_state["errors"] = 0
        scan_state["last"] = None
        try:
            async with _settings_session() as session:
                known = await GalleryRepository(session).signatures(_scan_roots())
            service = LibraryService(
                _scan_roots(),
                batch_size=_settings().scan_batch_size,
                known_signatures=known,
            )
            iterator = service.scan_batches()
            while True:
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
            async with _settings_session() as session, session.begin():
                expunged = await GalleryRepository(session).expunge_missing(
                    _scan_roots(), service.seen_path_hashes
                )
            scan_state["expunged"] = expunged
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
                            _enqueue_tag_sync(ids)
                            last_id = ids[-1]
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "tag sync enqueue failed", extra=log_extra(error=type(exc).__name__)
                    )
            counters = service.last_counters
            scan_state["last"] = {**counters.__dict__, "persisted": persisted, "expunged": expunged}
            logger.info("library scan persisted", extra=log_extra(**scan_state["last"]))
        except Exception as exc:  # noqa: BLE001
            scan_state["last"] = {"error": type(exc).__name__, "persisted": persisted}
            logger.error(
                "library scan persistence error", extra=log_extra(error=type(exc).__name__)
            )
        finally:
            scan_state["running"] = False
            try:
                if app.state.telegram is not None and _settings().telegram_chat_ids:
                    last = scan_state["last"] or {}
                    if last.get("error"):
                        await app.state.telegram.send_message(
                            f"Library scan failed: {last['error']}"
                        )
                    else:
                        await app.state.telegram.send_message(
                            "Library scan complete: "
                            f"{last.get('persisted', 0)} new, {last.get('expunged', 0)} removed"
                        )
            except Exception as exc:  # noqa: BLE001 - notification must not break the scan
                logger.warning(
                    "scan notification failed", extra=log_extra(error=type(exc).__name__)
                )


def _settings_session():
    return app.state.session_factory()


@app.post("/api/scan", status_code=202)
async def trigger_scan() -> dict[str, object]:
    if not scan_state["running"]:
        scan_state["running"] = True
        _spawn(_run_scan(), "library scan")
    return {"status": "running" if scan_state["running"] else "started"}


@app.get("/api/scan")
async def scan_status() -> dict[str, object]:
    return scan_state.copy()


@app.get("/api/tag-sync/status")
async def tag_sync_status() -> dict[str, object]:
    return dict(tag_sync_state)


@app.post("/api/tag-sync/refresh-categories", status_code=202)
async def trigger_category_refresh() -> dict[str, object]:
    """Start a one-time 大分类 backfill for galleries stuck in ``other``."""
    if not tag_sync_state["category_refresh_running"]:
        _spawn(_category_refresh_once(), "category refresh")
    return {"status": "running" if tag_sync_state["category_refresh_running"] else "started"}


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
        async def _on_progress(current: int, total: int) -> None:
            if task.id is not None and task.id in _download_cancelled:
                raise DownloadCancelledError("download was cancelled")
            await _download_progress(task.id, current, total)

        result = await app.state.downloader.execute(
            DownloadTask(task.gid, task.token, task.title, task.id, 1, task.mode, task.category),
            progress=_on_progress,
        )
        completed = False
        async with _settings_session() as session, session.begin():
            row = await session.get(DownloadTaskModel, task.id)
            if row and row.status != "cancelled":
                row.status, row.target_path, row.category = (
                    "success",
                    str(result.path),
                    result.category,
                )
                row.error_message = None
                row.finished_at = datetime.now(UTC)
            await DownloadRepository(session).record_attempt(
                task.id or 0, row.retry_count + 1, "success"
            )
            completed = True
        if completed and app.state.telegram is not None:
            await app.state.telegram.send_message(
                f"Download succeeded: {result.title or task.gid} ({result.pages} pages)"
            )
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
                    row.retry_count += 1
                    row.status = "pending" if row.retry_count < row.max_retries else "failed"
                    row.error_message = f"{type(exc).__name__}: {exc}"
                    if row.status == "failed":
                        row.finished_at = datetime.now(UTC)
                    await DownloadRepository(session).record_attempt(
                        task.id or 0, row.retry_count, "failed", type(exc).__name__
                    )
            if row is not None and row.status != "cancelled" and app.state.telegram is not None:
                await app.state.telegram.send_message(
                    f"Download failed: {task.title or task.gid} ({type(exc).__name__})"
                )
        except SQLAlchemyError as db_exc:
            logger.error(
                "download status persistence failed", extra=log_extra(error=type(db_exc).__name__)
            )


async def _download_worker_loop() -> None:
    """Recover and claim persisted jobs, so a process restart does not lose work."""
    try:
        async with _settings_session() as session, session.begin():
            await DownloadRepository(session).recover_orphans()
    except Exception as exc:  # noqa: BLE001 - worker must survive database outages
        logger.warning("download recovery failed", extra=log_extra(error=type(exc).__name__))
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


def _enqueue_tag_sync(gallery_ids: list[int]) -> int:
    """Queue gallery ids for background tag synchronization, de-duplicating."""
    added = 0
    for gallery_id in gallery_ids:
        if gallery_id not in tag_sync_queued:
            tag_sync_queued.add(gallery_id)
            tag_sync_queue.put_nowait(gallery_id)
            added += 1
    tag_sync_state["queued"] = tag_sync_queue.qsize()
    if added:
        current = int(tag_sync_state["total"] or 0)
        tag_sync_state["total"] = current + added
    return added
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
    translation_state["running"] = True
    try:
        data = await _fetch_translation_db()
        load_translations(reset=True)
        entries = merge_translation_data(data)
        translation_state["entries"] = entries
        translation_state["last"] = datetime.now(UTC).isoformat()
        translation_state["last_error"] = None
        logger.info("tag translations updated", extra=log_extra(entries=entries))
        return True
    except Exception as exc:  # noqa: BLE001 - a failed refresh must not stop the loop
        translation_state["last_error"] = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "tag translation update failed", extra=log_extra(error=type(exc).__name__)
        )
        return False
    finally:
        translation_state["running"] = False


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
    try:
        async with _settings_session() as session:
            last_id = 0
            seeded = 0
            while True:
                ids = await GalleryRepository(session).pending_tag_sync_ids(1000, last_id)
                if not ids:
                    break
                _enqueue_tag_sync(ids)
                seeded += len(ids)
                last_id = ids[-1]
            tag_sync_state["total"] = seeded + tag_sync_state["processed"]
    except Exception as exc:  # noqa: BLE001 - seeding must not kill the worker
        logger.warning("tag sync seeding failed", extra=log_extra(error=type(exc).__name__))
    logger.info("tag sync seeded", extra=log_extra(queued=tag_sync_queue.qsize()))
    tag_sync_state["running"] = True
    concurrency = max(1, _settings().tag_sync_concurrency)
    semaphore = asyncio.Semaphore(concurrency)
    base_interval = max(0.1, float(_settings().tag_sync_interval_seconds))
    interval = [base_interval]
    success_streak = [0]
    MAX_BACKOFF = 60.0
    MAX_ATTEMPTS = 8

    async def _sync_one(gallery_id: int) -> None:
        try:
            async with _settings_session() as session, session.begin():
                await TagSyncService(
                    app.state.eh_client, GalleryRepository(session)
                ).sync(gallery_id)
            tag_sync_state["succeeded"] += 1
            tag_sync_attempts.pop(gallery_id, None)
            success_streak[0] += 1
            if success_streak[0] >= 10 and interval[0] > base_interval:
                interval[0] = max(base_interval, interval[0] / 2)
        except GalleryGoneError as exc:
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
            tag_sync_state["failed"] += 1
            tag_sync_attempts.pop(gallery_id, None)
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
                attempts = tag_sync_attempts.get(gallery_id, 0) + 1
                if attempts <= MAX_ATTEMPTS:
                    tag_sync_attempts[gallery_id] = attempts
                    tag_sync_state["retries"] += 1
                    _enqueue_tag_sync([gallery_id])
                    return
            tag_sync_attempts.pop(gallery_id, None)
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

    async def _worker() -> None:
        while True:
            try:
                gallery_id = await asyncio.wait_for(tag_sync_queue.get(), timeout=5)
            except TimeoutError:
                tag_sync_state["queued"] = tag_sync_queue.qsize()
                tag_sync_state["running"] = tag_sync_queue.qsize() > 0
                continue
            tag_sync_queued.discard(gallery_id)
            async with semaphore:
                await _sync_one(gallery_id)
            tag_sync_state["processed"] += 1
            tag_sync_state["queued"] = tag_sync_queue.qsize()
            tag_sync_state["interval"] = interval[0]
            await asyncio.sleep(interval[0])

    workers = [asyncio.create_task(_worker()) for _ in range(concurrency)]
    try:
        await asyncio.gather(*workers)
    finally:
        tag_sync_state["running"] = False


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
    download_quality: str | None = None
    use_hah: bool | None = None
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
    auto_sync_tags: bool | None = None
    tag_sync_interval_seconds: float | None = Field(default=None, gt=0)
    tag_sync_concurrency: int | None = Field(default=None, ge=1, le=32)
    generate_thumbnails: bool | None = None

    @model_validator(mode="after")
    def validate_values(self) -> "SettingsRequest":
        if self.http_proxy and self.socks5_proxy:
            raise ValueError("configure only one proxy")
        if self.favorites_categories is not None and any(
            category not in range(10) for category in self.favorites_categories
        ):
            raise ValueError("favorites categories must be between 0 and 9")
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
        "download_quality": current.download_quality,
        "use_hah": current.use_hah,
        "title_display": current.title_display,
        "download_max_retries": 3,
        "favorites_categories": current.favorites_categories,
        "download_favorites_enabled": current.download_favorites_enabled,
        "favorites_poll_interval_minutes": current.favorites_poll_interval_minutes,
        "telegram_bot_configured": bool(current.telegram_bot_token),
        "telegram_chat_ids": current.telegram_chat_ids,
        "telegram_allowed_user_ids": current.telegram_allowed_user_ids,
        "auto_sync_tags": current.auto_sync_tags,
        "tag_sync_interval_seconds": current.tag_sync_interval_seconds,
        "tag_sync_concurrency": current.tag_sync_concurrency,
        "generate_thumbnails": current.generate_thumbnails,
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
        "download_quality",
        "use_hah",
        "title_display",
        "favorites_categories",
        "favorites_poll_interval_minutes",
        "telegram_bot_token",
        "telegram_chat_ids",
        "telegram_allowed_user_ids",
        "auto_sync_tags",
        "tag_sync_interval_seconds",
        "tag_sync_concurrency",
        "download_favorites_enabled",
        "auth_required",
        "tag_translation_update_interval_minutes",
        "generate_thumbnails",
    }
    updates = {key: value for key, value in values.items() if key in allowed}
    if "library_roots" in updates:
        updates["library_roots"] = normalize_library_roots(updates["library_roots"])
    app.state.settings = _settings().model_copy(update=updates)


@app.get("/api/settings")
async def settings_get() -> dict[str, object]:
    try:
        async with _settings_session() as session:
            persisted = await SettingsRepository(session).get()
        _update_runtime_settings(persisted)
    except Exception as exc:  # noqa: BLE001 - DB down: serve in-memory settings
        # DB unavailable: serve the current in-memory settings unchanged.
        logger.warning("settings could not be re-read", extra={"error": str(exc)})
    return _settings_public()


async def _save_settings(body: SettingsRequest) -> dict[str, object]:
    values = body.model_dump(exclude_none=True)
    if "library_roots" in values:
        values["library_roots"] = normalize_library_roots(values["library_roots"])
    # An empty input means "clear this proxy"; an empty string would be sent to
    # httpx verbatim and crash every outbound request.
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
            _favcat(item) for item in favorites if bool(item.get("enabled", True))
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
    if cookie_fields:
        values["exhentai_cookies"] = {**_settings().exhentai_cookies, **cookie_fields}
    _update_runtime_settings(values)
    persisted_values = {
        key: getattr(_settings(), key)
        for key in (
            "library_roots",
            "exhentai_base_url",
            "exhentai_cookies",
            "http_proxy",
            "socks5_proxy",
            "download_root",
            "download_concurrency",
            "favorites_categories",
            "download_favorites_enabled",
            "favorites_poll_interval_minutes",
            "auto_sync_tags",
            "tag_sync_interval_seconds",
            "tag_sync_concurrency",
            "tag_translation_update_interval_minutes",
            "generate_thumbnails",
        )
    }
    persisted_values.update(values)
    # All user-editable settings live in the DB (single source of truth).
    try:
        async with _settings_session() as session, session.begin():
            await SettingsRepository(session).save(persisted_values)
            for item in favorites:
                favcat = _favcat(item)
                row = await FavoritesRepository(session).category(favcat)
                if row is None:
                    from ..db.models import FavoritesMonitor

                    row = FavoritesMonitor(favcat=favcat)
                    session.add(row)
                row.enabled = bool(item.get("enabled", True))
                row.mode = str(item["mode"])
                row.poll_interval_seconds = max(
                    60, int(item.get("poll_interval_minutes", 720)) * 60
                )
    except Exception as exc:
        raise _db_error(exc) from exc
    await _refresh_services()
    return _settings_public()


async def _refresh_services() -> None:
    """Rebuild network-bound services so changed proxy/cookies apply immediately."""
    old_client = app.state.eh_client
    old_telegram = app.state.telegram
    if old_telegram is not None:
        await old_telegram.aclose()
    if old_client is not None:
        await old_client.aclose()
    client = EhClient(_settings())
    app.state.eh_client = client
    app.state.downloader = Downloader(
        client, _settings().download_root, concurrency=_settings().download_concurrency
    )
    app.state.telegram = TelegramNotifier(_settings())
    _start_telegram_bot()
    app.state.favorites_service = FavoritesService(
        client, _FavoritesRepositoryProxy(), _FavoriteDownloadQueue(), app.state.telegram
    )


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


@app.post("/api/settings")
async def settings_save(body: SettingsRequest) -> dict[str, object]:
    return await _save_settings(body)


@app.post("/api/settings/exhentai/test")
async def settings_test_exhentai() -> dict[str, str]:
    if not _settings().exhentai_cookies:
        return {"status": "not_configured", "message": "ExHentai Cookie 未设置"}
    try:
        response = await app.state.eh_client._get("/")
        return {"status": "ok", "message": f"HTTP {response.status_code}"}
    except Exception:  # noqa: BLE001
        return {"status": "failed", "message": "ExHentai 登录测试失败"}


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

    async def checked(self, favcat: int, success: bool):
        return await self._call("checked", favcat, success)


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


@app.post("/api/downloads", status_code=202)
async def create_download(body: DownloadRequest) -> dict[str, object]:
    try:
        async with _settings_session() as session, session.begin():
            task = await DownloadRepository(session).create(
                body.gid, body.token, body.title, body.mode, body.max_pages
            )
            if task is None:
                raise HTTPException(
                    status_code=409, detail="An active download already exists for this gid"
                )
            task_data = DownloadTask(
                task.gid,
                task.token,
                task.title or str(task.gid),
                task.id,
                task.max_retries,
                max_pages=body.max_pages,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc
    downloader = app.state.downloader
    if downloader is None:
        raise HTTPException(status_code=503, detail="Downloader is unavailable")
    return {"id": task_data.id, "gid": task_data.gid, "status": "pending"}


@app.get("/api/downloads")
async def list_downloads(
    page: int = 1, page_size: int = 24, status: str | None = None
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(status_code=422, detail="invalid pagination")
    try:
        async with _settings_session() as session:
            total, rows = await DownloadRepository(session).list_page(page, page_size, status)
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": x.id,
                "gid": x.gid,
                "title": x.title,
                "status": x.status,
                "retry_count": x.retry_count,
                "max_retries": x.max_retries,
                "current_page": x.current_page or 0,
                "total_pages": x.total_pages,
                "error_message": x.error_message,
            }
            for x in rows
        ],
    }


@app.post("/api/downloads/{task_id}/retry")
async def retry_download(task_id: int) -> dict[str, object]:
    try:
        async with _settings_session() as session, session.begin():
            row = await session.get(DownloadTaskModel, task_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Download task not found")
            if row.status not in {"failed", "cancelled", "success"}:
                raise HTTPException(status_code=409, detail="Task is still active")
            row.status = "pending"
            row.retry_count = 0
            row.error_message = None
            row.finished_at = None
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    return {"id": task_id, "status": "pending"}


@app.post("/api/downloads/{task_id}/cancel")
async def cancel_download(task_id: int) -> dict[str, object]:
    try:
        async with _settings_session() as session, session.begin():
            if not await DownloadRepository(session).cancel(task_id):
                raise HTTPException(status_code=404, detail="Download task not found")
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    _download_cancelled.add(task_id)
    return {"id": task_id, "status": "cancelled"}


@app.delete("/api/downloads/{task_id}", status_code=204)
async def delete_download_task(task_id: int) -> None:
    try:
        async with _settings_session() as session, session.begin():
            if not await DownloadRepository(session).delete(task_id):
                raise HTTPException(status_code=404, detail="Download task not found")
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc


@app.get("/api/favorites/categories")
async def favorite_categories() -> list[dict[str, object]]:
    try:
        async with _settings_session() as session:
            rows = await FavoritesRepository(session).categories()
            stats = await FavoritesRepository(session).counts_and_sizes()
            breakdown = {
                row.favcat: await FavoritesRepository(session).cloud_size_breakdown(row.favcat)
                for row in rows
            }
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    live_counts: dict[int, int] = {}
    try:
        live_counts = await _favorite_counts_cached()
    except Exception as exc:  # noqa: BLE001 - fall back to recorded counts
        logger.warning(
            "could not fetch live favorite counts", extra=log_extra(error=type(exc).__name__)
        )
    result = []
    for x in rows:
        cloud, local, local_size = stats.get(x.favcat, (0, 0, 0))
        cloud_count = live_counts.get(x.favcat, cloud)
        known, unknown = breakdown.get(x.favcat, (0, 0))
        if unknown > 0 and local > 0:
            known += int((local_size / local) * unknown)  # estimate the unfetched tail
        result.append(
            {
                "favcat": x.favcat,
                "name": x.name,
                "enabled": x.enabled,
                "mode": x.mode,
                "poll_interval_minutes": max(1, round(x.poll_interval_seconds / 60)),
                "cloud_count": cloud_count,
                "local_count": local,
                "local_size": local_size,
                "cloud_size": known or _estimate_cloud_size(cloud_count, local, local_size),
            }
        )
    return result


@app.post("/api/favorites/compute-sizes", status_code=202)
async def compute_favorite_sizes() -> dict[str, object]:
    """Fetch missing gallery sizes in the background for exact cloud sizes."""
    async with _settings_session() as session:
        favcats = [row.favcat for row in await FavoritesRepository(session).categories()]
    for favcat in favcats:
        _spawn(_favorite_size_sync(favcat), f"favorite size sync {favcat}")
    return {"status": "started", "favcats": favcats}


_FAV_COUNTS_TTL = 300.0
_fav_counts_cache: dict[str, object] = {"ts": 0.0, "counts": {}}


async def _favorite_counts_cached() -> dict[int, int]:
    """Live per-folder gallery counts, cached for ``_FAV_COUNTS_TTL`` seconds."""
    import time as _time

    now = _time.time()
    if now - float(_fav_counts_cache["ts"]) < _FAV_COUNTS_TTL:
        return dict(_fav_counts_cache["counts"])  # type: ignore[arg-type]
    if app.state.eh_client is not None:
        counts = await app.state.eh_client.fetch_favorite_counts()
        _fav_counts_cache["ts"] = now
        _fav_counts_cache["counts"] = counts
        return counts
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
    """Fetch missing gallery sizes from ExHentai into favorite_items.file_size.

    Runs in the background so the folder check itself stays fast; the exact
    size improves the cloud-size figure on the Favorites page.
    """
    try:
        async with _settings_session() as session:
            pending = await FavoritesRepository(session).pending_size_gids(favcat)
        if not pending:
            return
        client = app.state.eh_client
        if client is None:
            return
        semaphore = asyncio.Semaphore(4)

        async def fetch_one(gid: int, token: str) -> tuple[int, int | None]:
            async with semaphore:
                try:
                    meta = await client.fetch_gallery_metadata(gid, token)
                    return gid, meta.file_size
                except Exception:  # noqa: BLE001 - one gallery must not block the sync
                    return gid, None

        results = await asyncio.gather(*(fetch_one(gid, token) for gid, token in pending))
        sizes = {gid: size for gid, size in results if size}
        async with _settings_session() as session, session.begin():
            for gid, size in sizes.items():
                await FavoritesRepository(session).set_file_size(favcat, gid, size)
        logger.info(
            "favorite sizes synced", extra=log_extra(favcat=favcat, fetched=len(sizes))
        )
    except Exception as exc:  # noqa: BLE001 - background task must not crash
        logger.warning(
            "favorite size sync failed", extra=log_extra(favcat=favcat, error=type(exc).__name__)
        )


@app.post("/api/favorites/categories")
async def update_favorite_category(
    body: FavoriteCategoryRequest, favcat: int = 0
) -> dict[str, object]:
    favcat = body.favcat if body.favcat is not None else favcat
    if not 0 <= favcat <= 9:
        raise HTTPException(status_code=422, detail="invalid favcat")
    try:
        async with _settings_session() as session, session.begin():
            row = await FavoritesRepository(session).category(favcat)
            if row is None:
                from ..db.models import FavoritesMonitor

                row = FavoritesMonitor(favcat=favcat)
                session.add(row)
            if body.enabled is not None:
                row.enabled = body.enabled
            if body.mode is not None:
                row.mode = body.mode
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    return {"favcat": favcat, "enabled": row.enabled, "mode": row.mode}


@app.post("/api/favorites/sync-categories")
async def sync_favorite_categories() -> list[dict[str, object]]:
    if not _settings().exhentai_cookies:
        raise HTTPException(status_code=422, detail="ExHentai Cookie 未设置")
    try:
        names = await app.state.eh_client.fetch_favorite_categories()
        async with _settings_session() as session, session.begin():
            for favcat, name in names.items():
                row = await FavoritesRepository(session).category(favcat)
                if row is None:
                    from ..db.models import FavoritesMonitor

                    row = FavoritesMonitor(favcat=favcat)
                    session.add(row)
                row.name = name
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "favorite category synchronization failed", extra=log_extra(error=type(exc).__name__)
        )
        raise HTTPException(status_code=503, detail="无法读取 ExHentai 收藏夹分类") from exc
    return [{"favcat": favcat, "name": name} for favcat, name in names.items()]


@app.post("/api/favorites/{favcat}/check", status_code=202)
async def check_favorites(favcat: int) -> dict[str, object]:
    if not 0 <= favcat <= 9:
        raise HTTPException(status_code=422, detail="invalid favcat")
    service = app.state.favorites_service
    if service is None:
        raise HTTPException(status_code=503, detail="Favorites service is unavailable")
    _spawn(_run_favorites_check(favcat, service), "favorites check")
    return {"status": "started", "favcat": favcat}


async def _run_favorites_check(favcat: int, service: FavoritesService) -> None:
    async with _settings_session() as session:
        category = await FavoritesRepository(session).category(favcat)
    # A disabled folder is check-only: record entries but never download. It
    # only starts downloading once the user enables the folder.
    if category is not None and not category.enabled:
        await service.check_category(favcat, mode="monitor_only")
    else:
        await service.check_category(favcat, mode=category.mode if category else "incremental")
    _spawn(_favorite_size_sync(favcat), f"favorite size sync {favcat}")


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
                _spawn(_run_favorites_check(favcat, service), "scheduled favorites check")
                logger.info("scheduled favorites check", extra=log_extra(favcat=favcat))
            except Exception as exc:  # noqa: BLE001 - one category must not stop the scheduler
                logger.error(
                    "scheduled favorites check failed",
                    extra=log_extra(favcat=favcat, error=type(exc).__name__),
                )


@app.get("/api/galleries")
async def gallery_list(
    page: int = 1,
    page_size: int = 24,
    q: str | None = None,
    tags: str | None = None,
    tag_mode: str = "or",
    tag_match: str = "exact",
    category: str | None = None,
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(
            status_code=422, detail="page must be >= 1 and page_size must be between 1 and 100"
        )
    if tag_mode not in {"and", "or"} or tag_match not in {"exact", "fuzzy"}:
        raise HTTPException(status_code=422, detail="invalid tag_mode or tag_match")
    if category == "":
        category = None
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="invalid category")
    parsed_tags: list[tuple[str | None, str]] = []
    for value in (tags or "").split(","):
        value = value.strip()
        if not value:
            continue
        if ":" in value:
            namespace, name = value.split(":", 1)
            namespace = namespace.strip() or None
        else:
            namespace, name = None, value
        if not name.strip() or len(name) > 200 or (namespace and len(namespace) > 32):
            raise HTTPException(status_code=422, detail="invalid tag")
        parsed_tags.append((namespace, name.strip()))
    try:
        async with _settings_session() as session:
            total, rows = await GalleryRepository(session).list_page(
                page, page_size, q, parsed_tags, tag_mode, tag_match, category
            )
            tag_map = await GalleryRepository(session).tags_for_galleries([row.id for row in rows])
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "q": q or "",
        "tags": tags or "",
        "tag_mode": tag_mode,
        "tag_match": tag_match,
        "category": category or "",
        "items": [
            {
                "id": row.id,
                "gid": row.gid,
                "title": display_title(row),
                "title_english": row.title,
                "title_jpn": row.title_jpn,
                "storage_type": row.storage_type,
                "category": row.category or "other",
                "page_count": row.page_count or 0,
                "cover_url": f"/api/galleries/{row.id}/thumb/0" if row.page_count else None,
                "tags": [
                    {"namespace": namespace, "name": name, "display": translated_tag(namespace, name)[1]}
                    for namespace, name in tag_map.get(row.id, [])
                ],
            }
            for row in rows
        ],
    }


async def _gallery(identifier: int) -> tuple[Gallery, list[GalleryPage]]:
    try:
        async with _settings_session() as session:
            result = await session.execute(
                select(Gallery).where((Gallery.gid == identifier) | (Gallery.id == identifier))
            )
            row = result.scalar_one_or_none()
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


@app.get("/api/galleries/random")
async def gallery_random() -> dict[str, object]:
    try:
        async with _settings_session() as session:
            gallery_id = await GalleryRepository(session).random_id()
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    if gallery_id is None:
        raise HTTPException(status_code=404, detail="No galleries available")
    return {"id": gallery_id}


@app.get("/api/galleries/{identifier}")
async def gallery_detail(identifier: int) -> dict[str, object]:
    row, pages = await _gallery(identifier)
    tags = await _gallery_tags(row.id)
    source_meta = row.source_meta or {}
    spider_keys = (
        "version",
        "start_page",
        "gid",
        "token",
        "mode",
        "preview_pages",
        "preview_per_page",
        "pages",
        "p_tokens",
        "page_entries",
        "warnings",
    )
    return {
        "id": row.id,
        "gid": row.gid,
        "title": display_title(row),
        "title_english": row.title,
        "title_jpn": row.title_jpn,
        "storage_type": row.storage_type,
        "category": row.category or "other",
        "page_count": len(pages),
        "pages": [
            {"index": p.page_index, "name": p.member_name, "media_type": p.media_type}
            for p in pages
        ],
        "warnings": source_meta.get("warnings", []),
        "spider_info": {key: source_meta[key] for key in spider_keys if key in source_meta},
        "tags": [
            {"namespace": namespace, "name": name, "display": translated_tag(namespace, name)[1]}
            for namespace, name in tags
        ],
        "tags_synced_at": row.tags_synced_at,
    }


class ProgressRequest(BaseModel):
    current_page: int = Field(ge=0)
    total_pages: int | None = Field(default=None, ge=0)


@app.get("/api/galleries/{identifier}/progress")
async def gallery_progress(identifier: int) -> dict[str, object]:
    row, pages = await _gallery(identifier)
    async with _settings_session() as session:
        progress = await GalleryRepository(session).progress(row.id)
    return {
        "gallery_id": row.id,
        "current_page": progress.current_page if progress else 0,
        "total_pages": progress.total_pages if progress else len(pages),
        "updated_at": progress.updated_at if progress else None,
    }


@app.put("/api/galleries/{identifier}/progress")
async def save_gallery_progress(identifier: int, body: ProgressRequest) -> dict[str, object]:
    row, pages = await _gallery(identifier)
    if body.current_page >= len(pages):
        raise HTTPException(status_code=422, detail="current_page is outside gallery")
    async with _settings_session() as session, session.begin():
        progress = await GalleryRepository(session).upsert_progress(
            row.id, body.current_page, body.total_pages or len(pages)
        )
        await GalleryRepository(session).record_history(
            row.id, body.current_page, body.total_pages or len(pages)
        )
    return {
        "gallery_id": row.id,
        "current_page": progress.current_page,
        "total_pages": progress.total_pages,
    }


@app.get("/api/history")
async def history(page: int = 1, page_size: int = 24) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(status_code=422, detail="invalid pagination")
    async with _settings_session() as session:
        total, rows = await GalleryRepository(session).history_page(page, page_size)
        galleries = (
            {
                row.id: row
                for row in (
                    await session.scalars(
                        select(Gallery).where(Gallery.id.in_({x.gallery_id for x in rows}))
                    )
                ).all()
            }
            if rows
            else {}
        )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "gallery_id": x.gallery_id,
                "current_page": x.current_page,
                "total_pages": x.total_pages,
                "last_read_at": x.last_read_at,
                "title": galleries[x.gallery_id].title if x.gallery_id in galleries else None,
                "url": f"/galleries/{x.gallery_id}",
            }
            for x in rows
        ],
    }


@app.delete("/api/history", status_code=204)
async def clear_history() -> None:
    async with _settings_session() as session, session.begin():
        await GalleryRepository(session).clear_history()


class BulkDeleteRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)
    delete_files: bool = False


def _remove_gallery_files(gallery: Gallery) -> None:
    """Delete the on-disk gallery directory if we own it (storage_path under a root)."""
    path_text = getattr(gallery, "storage_path", None)
    if not path_text:
        return
    path = Path(path_text)
    try:
        owned = False
        try:
            owned = any(path.is_relative_to(root) for root in _scan_roots())
        except (ValueError, TypeError):
            owned = False
        if path.is_dir() and owned:
            import shutil as _shutil

            _shutil.rmtree(path, ignore_errors=True)
    except OSError:
        logger.warning("gallery file removal failed", extra={"path": str(path)})


@app.delete("/api/galleries/{identifier}", status_code=204)
async def delete_gallery(identifier: int, delete_files: bool = False) -> None:
    try:
        async with _settings_session() as session, session.begin():
            gallery = await GalleryRepository(session).delete_by_identifier(identifier)
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    if gallery is None:
        raise HTTPException(status_code=404, detail="Gallery not found")
    if delete_files:
        _remove_gallery_files(gallery)


@app.post("/api/galleries/delete-bulk")
async def delete_galleries_bulk(body: BulkDeleteRequest) -> dict[str, object]:
    if not body.ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    try:
        async with _settings_session() as session, session.begin():
            rows = await session.scalars(
                select(Gallery).where(Gallery.id.in_(body.ids))
            )
            galleries = list(rows)
            removed = await GalleryRepository(session).delete_ids([g.id for g in galleries])
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    if body.delete_files:
        for gallery in galleries:
            _remove_gallery_files(gallery)
    return {"deleted": removed}


@app.post("/api/galleries/{identifier}/sync-tags")
async def sync_gallery_tags(identifier: int, redirect: bool = False):
    try:
        async with _settings_session() as session, session.begin():
            result = await TagSyncService(app.state.eh_client, GalleryRepository(session)).sync(
                identifier
            )
    except GalleryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (GalleryGidMissing, GalleryTokenMissing) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        logger.warning(
            "ExHentai tag synchronization failed", extra=log_extra(error=type(exc).__name__)
        )
        raise HTTPException(status_code=502, detail="ExHentai metadata request failed") from exc
    if redirect:
        return RedirectResponse(f"/galleries/{identifier}", status_code=303)
    return result


@app.get("/api/galleries/{identifier}/pages/{page_index}")
async def gallery_page(identifier: int, page_index: int) -> StreamingResponse:
    row, pages = await _gallery(identifier)
    page = next((item for item in pages if item.page_index == page_index), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    scanner = registry.for_path(Path(row.storage_path))
    if scanner is None:
        raise HTTPException(status_code=500, detail="No scanner for gallery")
    stream = await run_in_threadpool(
        scanner.open_page,
        _meta(row, pages),
        PageInfo(page.page_index, page.member_name, page.media_type),
    )
    return StreamingResponse(
        _closing_stream(stream), media_type=_page_media_type(page.media_type)
    )


def _page_media_type(ext: str) -> str:
    """Map a page file extension to a standards-compliant media type."""
    return {"jpg": "image/jpeg", "jpe": "image/jpeg", "jpeg": "image/jpeg"}.get(
        (ext or "").lower(), f"image/{ext}"
    )


def _closing_stream(stream: BinaryIO) -> Iterator[bytes]:
    """Yield a sync page stream, closing the underlying file when exhausted.

    StreamingResponse iterates sync iterators in a threadpool but never closes
    a raw file object, so every served page would leak a file descriptor.
    """
    try:
        yield from stream
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
            service.get_or_create(gallery_id, page.page_index, data)
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
    added = 0
    missing_total = 0
    for gallery_id, page_count in pairs:
        if service.cached(gallery_id, 0) is not None:
            continue
        missing_total += 1
        if gallery_id in thumb_queued:
            continue
        thumb_queued.add(gallery_id)
        thumb_queue.put_nowait(gallery_id)
        added += 1
    thumb_state["total"] = missing_total
    thumb_state["queued"] = thumb_queue.qsize()
    if added:
        thumb_state["running"] = True
    logger.info(
        "thumbnail seeding complete", extra=log_extra(queued=added, pending=missing_total)
    )


async def _thumbnail_worker_loop() -> None:
    concurrency = 4
    thumb_state["running"] = True

    async def _worker() -> None:
        while True:
            try:
                gallery_id = await asyncio.wait_for(thumb_queue.get(), timeout=5)
            except TimeoutError:
                # Queue drained: reflect idle so the task-progress UI hides.
                thumb_state["running"] = thumb_queue.qsize() > 0
                thumb_state["queued"] = thumb_queue.qsize()
                continue
            thumb_queued.discard(gallery_id)
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
            thumb_state["queued"] = thumb_queue.qsize()

    workers = [asyncio.create_task(_worker()) for _ in range(concurrency)]
    try:
        await asyncio.gather(*workers)
    finally:
        thumb_state["running"] = thumb_queue.qsize() > 0


@app.get("/api/galleries/{identifier}/thumb/{page_index}")
async def gallery_thumbnail(identifier: int, page_index: int) -> FileResponse:
    row, pages = await _gallery(identifier)
    page = next((item for item in pages if item.page_index == page_index), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    scanner = registry.for_path(Path(row.storage_path))
    if scanner is None:
        raise HTTPException(status_code=500, detail="No scanner for gallery")
    service = _thumb_service()
    cached = service.cached(row.id, page_index)
    if cached is None:
        stream = await run_in_threadpool(
            scanner.open_page,
            _meta(row, pages),
            PageInfo(page.page_index, page.member_name, page.media_type),
        )
        try:
            data = await run_in_threadpool(stream.read)
        finally:
            try:
                stream.close()
            except OSError:
                pass
        try:
            cached = await run_in_threadpool(
                service.get_or_create, row.id, page_index, data
            )
        except ThumbnailError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(
        cached,
        media_type=JPEG_MIME,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/thumbs/status")
async def thumb_status() -> dict[str, object]:
    return dict(thumb_state)


@app.post("/api/thumbs/generate", status_code=202)
async def trigger_thumbnail_generation() -> dict[str, object]:
    """Queue every gallery missing thumbnails for background generation."""
    await _seed_thumbnails()
    thumb_state["running"] = True
    return {
        "status": "running" if thumb_queue.qsize() else "started",
        "queued": thumb_queue.qsize(),
    }


@app.post("/api/tag-sync/start", status_code=202)
async def trigger_tag_sync() -> dict[str, object]:
    """Re-queue every gallery that still needs tag sync (manual full run)."""
    async with _settings_session() as session:
        last_id = 0
        seeded = 0
        while True:
            ids = await GalleryRepository(session).pending_tag_sync_ids(1000, last_id)
            if not ids:
                break
            _enqueue_tag_sync(ids)
            seeded += len(ids)
            last_id = ids[-1]
    return {"status": "started", "queued": seeded}


@app.get("/api/tags/search")
async def tag_search(
    q: str | None = None,
    namespace: str | None = None,
    page: int = 1,
    page_size: int = 60,
    zh: bool = False,
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(status_code=422, detail="invalid pagination")
    # Chinese autocomplete: reverse-search the translation table.
    if zh and q and q.strip():
        from ..services.tag_translation import search_zh

        matched = search_zh(q, limit=page_size)
        # Attach real usage counts for the matched (namespace, name) pairs.
        async with _settings_session() as session:
            repo = GalleryRepository(session)
            rows = await repo.tag_counts_for(matched)
        counts = {(ns, name): count for ns, name, count in rows}
        return {
            "total": len(matched),
            "page": 1,
            "page_size": page_size,
            "facets": [],
            "items": [
                {
                    "namespace": ns,
                    "name": name,
                    "display": display,
                    "usage_count": counts.get((ns, name), 0),
                }
                for ns, name, display in matched
            ],
        }
    async with _settings_session() as session:
        repo = GalleryRepository(session)
        total, rows = await repo.search_tags(q, page, page_size, namespace)
        facets = await repo.tag_facets() if not namespace else []
    facet_items = [
        {"namespace": name, "total": count}
        for name, count in sorted(facets, key=lambda x: -x[1])
    ]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "facets": facet_items,
        "items": [
            {"namespace": namespace, "name": name, "display": translated_tag(namespace, name)[1], "usage_count": count}
            for namespace, name, count in rows
        ],
    }


@app.get("/api/tags/search/status")
async def tag_translation_status() -> dict[str, object]:
    return {
        **translation_state,
        "entries": translation_entry_count(),
        "source": _TRANSLATION_RELEASE_API,
        "interval_minutes": _settings().tag_translation_update_interval_minutes,
    }


@app.post("/api/tags/search/reload", status_code=202)
async def tag_translation_reload() -> dict[str, object]:
    ok = await _translation_update_once()
    return {"accepted": True, "ok": ok, "last_error": translation_state["last_error"]}


@app.post("/api/telegram/test")
async def telegram_test() -> dict[str, object]:
    notifier = app.state.telegram
    if notifier is None or not _settings().telegram_bot_token:
        raise HTTPException(status_code=422, detail="Telegram bot token is not configured")
    targets = _settings().telegram_chat_ids
    if not targets:
        raise HTTPException(status_code=422, detail="No Telegram chat IDs configured")
    results: dict[str, object] = {}
    for chat_id in targets:
        results[str(chat_id)] = await notifier.send_message(
            "GalleryVault: Telegram 连接测试 OK", chat_id=chat_id
        )
    ok = all(results.values())
    return {"ok": ok, "results": results}


@app.get("/api/auth/session")
async def auth_session() -> dict[str, object]:
    return {
        "authenticated": True,
        "auth_required": _settings().auth_required,
        "must_change_password": _must_change_password(),
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
    try:
        async with _settings_session() as session, session.begin():
            await SettingsRepository(session).save_extra({"auth_password_hash": new_hash})
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    # Force sync so the new hash is effective immediately.
    await _apply_persisted_settings()
    logger.info("account password changed")

