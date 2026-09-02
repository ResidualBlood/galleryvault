"""Lifespan, startup preparation, and background worker lifecycle management."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..config import get_settings
from ..db.models import AppConfig
from ..db.models import DownloadTask as DownloadTaskModel
from ..db.repository import SettingsRepository
from ..logging import log_extra
from ..secrets import (
    decrypt_or_plain,
    encrypt,
    encrypt_json,
    encryption_enabled,
    is_encrypted,
)
from ..services.settings_service import (
    decrypt_user_settings,
    start_telegram_bot,
    update_runtime_settings,
)
from .dependencies import spawn_task
from .state import app_state, create_services, sync_state

logger = logging.getLogger(__name__)

translation_update_task: asyncio.Task | None = None


async def warmup_database_pool(session_factory: Any) -> None:
    """Warm up the async engine connection pool."""
    if not session_factory:
        return
    try:
        async with session_factory() as session:
            await session.execute(select(1))
    except Exception as exc:  # noqa: BLE001
        logger.warning("database pool warmup failed", extra=log_extra(error=type(exc).__name__))


async def cleanup_partial_downloads(download_root: str | Path, session_factory: Any) -> None:
    """Sweep temporary partial download folders (.gv-*) that are no longer active."""
    try:
        keep_gids: set[int] = set()
        if session_factory:
            try:
                async with session_factory() as session:
                    rows = await session.execute(
                        select(DownloadTaskModel.gid).where(
                            DownloadTaskModel.status.in_(["pending", "downloading"])
                        )
                    )
                    keep_gids = {int(row[0]) for row in rows}
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "could not read active downloads for temp sweep",
                    extra=log_extra(error=type(exc).__name__),
                )
        root = Path(download_root)
        if not root.exists():
            return
        for child in root.glob(".gv-*"):
            gid_text = child.name[len(".gv-") :] if child.name.startswith(".gv-") else ""
            if gid_text.isdigit() and int(gid_text) in keep_gids:
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("partial download cleanup failed", extra=log_extra(error=type(exc).__name__))


async def stop_background_tasks(
    spawned_tasks: set[asyncio.Task] | None = None,
    specific_tasks: list[asyncio.Task | None] | None = None,
) -> None:
    """Gracefully cancel and await background tasks during shutdown."""
    tasks_to_cancel: set[asyncio.Task] = set(spawned_tasks or set())
    for t in specific_tasks or []:
        if t is not None:
            tasks_to_cancel.add(t)
    for task in list(tasks_to_cancel):
        if not task.done():
            with contextlib.suppress(Exception):
                task.cancel()
    for task in list(tasks_to_cancel):
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


def hydrate_startup_logs(max_lines: int = 500) -> None:
    """Hydrate memory ring buffer from historical log files during startup."""
    try:
        from ..logging import hydrate_recent_logs

        hydrate_recent_logs(max_lines=max_lines)
    except Exception as exc:
        logger.debug("startup log hydration skipped", exc_info=exc)


async def bootstrap_auth() -> None:
    if not app_state.session_factory:
        return
    settings = app_state.settings or get_settings()
    async with app_state.session_factory() as session:
        row = await session.get(AppConfig, "runtime_auth")
        runtime = dict(row.value) if row and isinstance(row.value, dict) else {}

    updates_dict: dict[str, object] = {}
    if not runtime.get("auth_secret"):
        if settings.auth_secret:
            updates_dict["auth_secret"] = settings.auth_secret
        else:
            updates_dict["auth_secret"] = secrets.token_urlsafe(32)
    if settings.auth_password_hash and not runtime.get("auth_password_hash"):
        updates_dict["auth_password_hash"] = settings.auth_password_hash

    if updates_dict:
        merged = {**runtime, **updates_dict}
        if encryption_enabled():
            for key in ("auth_secret", "auth_password_hash"):
                if isinstance(merged.get(key), str):
                    merged[key] = encrypt(merged[key])
        async with app_state.session_factory() as session, session.begin():
            row = await session.get(AppConfig, "runtime_auth")
            if row is None:
                session.add(AppConfig(key="runtime_auth", value=merged))
            else:
                row.value = merged

    async with app_state.session_factory() as session:
        row = await session.get(AppConfig, "runtime_auth")
        final = dict(row.value) if row and isinstance(row.value, dict) else {}

    opts: dict[str, object] = {"auth_secret": decrypt_or_plain(final.get("auth_secret"))}
    if final.get("auth_password_hash"):
        opts["auth_password_hash"] = decrypt_or_plain(final["auth_password_hash"])
    updated = settings.model_copy(update=opts)
    app_state.settings = updated
    sync_state()


async def migrate_plaintext_secrets() -> None:
    if not encryption_enabled() or not app_state.session_factory:
        return
    try:
        async with app_state.session_factory() as session, session.begin():
            runtime_row = await session.get(AppConfig, "runtime_auth")
            if runtime_row is not None and isinstance(runtime_row.value, dict):
                value = dict(runtime_row.value)
                changed = False
                for key in ("auth_secret", "auth_password_hash"):
                    v = value.get(key)
                    if isinstance(v, str) and v and not is_encrypted(v):
                        value[key] = encrypt(v)
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
        logger.info("at-rest secret encryption enabled; plaintext values migrated")
    except Exception as exc:  # noqa: BLE001
        logger.warning("plaintext secret migration failed", extra=log_extra(error=str(exc)))


def ensure_translation_updater() -> asyncio.Task | None:
    global translation_update_task
    settings = app_state.settings or get_settings()
    if (
        translation_update_task is not None
        and not translation_update_task.done()
        and settings.tag_translation_update_interval_minutes <= 0
    ):
        task = translation_update_task
        translation_update_task = None
        task.cancel()
        return None

    if (
        translation_update_task is None or translation_update_task.done()
    ) and settings.tag_translation_update_interval_minutes > 0:
        from ..services.tag_sync_worker import translation_update_loop

        task = spawn_task(translation_update_loop(), "translation updater")
        if task is not None:
            translation_update_task = task
        else:
            try:
                translation_update_task = asyncio.create_task(translation_update_loop())
            except RuntimeError:
                pass
    return translation_update_task


async def startup() -> None:
    sync_state()
    hydrate_startup_logs()

    enable_workers = app_state.extra.get("enable_workers", True)

    # Warm up database pool
    await warmup_database_pool(app_state.session_factory)

    if not enable_workers:
        sync_state()
        return

    # Full production startup
    try:
        if app_state.session_factory:
            async with app_state.session_factory() as session:
                persisted = await SettingsRepository(session).get()
            update_runtime_settings(decrypt_user_settings(persisted))
    except Exception:  # noqa: BLE001
        logger.warning("user settings could not be loaded at startup")

    try:
        await bootstrap_auth()
        await migrate_plaintext_secrets()
        await app_state.task_manager.restore_history()
    except Exception:  # noqa: BLE001
        logger.warning("auth bootstrap failed; using temporary credentials")

    settings_obj = app_state.settings or get_settings()
    services = create_services(settings_obj)
    for key, obj in services.items():
        setattr(app_state, key, obj)

    start_telegram_bot()
    sync_state()

    # Background tasks
    from ..services.download_worker import (
        download_retry_sweep_loop,
        download_worker_loop,
        telegram_flush_loop,
    )
    from ..services.favorites_worker import (
        favorites_poll_loop,
        refresh_favorite_counts,
    )
    from ..services.tag_sync_worker import tag_sync_worker_loop
    from ..services.tag_translation import load_translations
    from ..services.thumbnail_worker import seed_thumbnails, thumbnail_worker_loop
    from ..services.updates_worker import gallery_updates_finalize_loop

    poll_coro = favorites_poll_loop()
    poll_task = spawn_task(poll_coro, "favorites poll")
    if poll_task is None:
        try:
            poll_task = asyncio.create_task(poll_coro)
        except RuntimeError:
            if hasattr(poll_coro, "close"):
                poll_coro.close()
            poll_task = None
    if poll_task is not None:
        app_state.extra["favorite_poll_task"] = poll_task

    spawn_task(refresh_favorite_counts(), "favorite counts startup warmup")
    try:
        from ..services.eh_client import probe_cookie_health

        spawn_task(probe_cookie_health(), "cookie health startup probe")
    except Exception:  # noqa: BLE001, S110
        pass
    await cleanup_partial_downloads(settings_obj.download_root, app_state.session_factory)

    app_state.extra["download_worker_task"] = asyncio.create_task(download_worker_loop())
    app_state.extra["download_retry_sweep_task"] = asyncio.create_task(download_retry_sweep_loop())
    app_state.extra["gallery_updates_finalize_task"] = asyncio.create_task(gallery_updates_finalize_loop())
    app_state.extra["telegram_flush_task"] = asyncio.create_task(telegram_flush_loop())
    app_state.extra["tag_sync_worker_task"] = asyncio.create_task(tag_sync_worker_loop())
    app_state.extra["thumb_worker_task"] = asyncio.create_task(thumbnail_worker_loop())

    if not encryption_enabled():
        logger.warning(
            "ENCRYPTION_KEY not set; exhentai_cookies and auth secrets will be stored in plaintext. "
            "Set ENCRYPTION_KEY to enable at-rest encryption and avoid plaintext persistence."
        )
    if settings_obj.generate_thumbnails:
        seed_coro = seed_thumbnails()
        seed_task = spawn_task(seed_coro, "thumbnail seeding startup")
        if seed_task is None:
            try:
                await seed_coro
            except Exception as exc:  # noqa: BLE001
                logger.warning("thumbnail seeding failed", extra=log_extra(error=type(exc).__name__))

    ensure_translation_updater()
    try:
        coro = asyncio.to_thread(load_translations)
        t = spawn_task(coro, "load translations")
        if t is None:
            await coro
    except RuntimeError:
        try:
            await asyncio.to_thread(load_translations)
        except Exception:  # noqa: BLE001, S110
            pass

    logger.info("GalleryVault started", extra=log_extra(library_roots=settings_obj.library_roots))
    sync_state()


async def shutdown() -> None:
    all_spawned: set[asyncio.Task] = set(app_state.extra.get("spawned_tasks", set()))
    specific = [
        translation_update_task,
        app_state.extra.get("favorite_poll_task"),
        app_state.extra.get("telegram_bot_task"),
        app_state.extra.get("download_worker_task"),
        app_state.extra.get("download_retry_sweep_task"),
        app_state.extra.get("gallery_updates_finalize_task"),
        app_state.extra.get("telegram_flush_task"),
        app_state.extra.get("tag_sync_worker_task"),
        app_state.extra.get("thumb_worker_task"),
    ]
    await stop_background_tasks(all_spawned, specific)
    if app_state.telegram is not None:
        if hasattr(app_state.telegram, "flush_summary") and callable(app_state.telegram.flush_summary):
            with contextlib.suppress(Exception):
                await app_state.telegram.flush_summary()
        if hasattr(app_state.telegram, "aclose") and callable(app_state.telegram.aclose):
            with contextlib.suppress(Exception):
                await app_state.telegram.aclose()
        app_state.telegram = None
    if app_state.eh_client is not None:
        if hasattr(app_state.eh_client, "aclose") and callable(app_state.eh_client.aclose):
            with contextlib.suppress(Exception):
                await app_state.eh_client.aclose()
        app_state.eh_client = None
    app_state.downloader = None
    app_state.favorites_service = None
    app_state.library_service = None
    app_state.thumbnail_service = None
    if isinstance(app_state.extra.get("spawned_tasks"), set):
        app_state.extra["spawned_tasks"].clear()
    if app_state.engine is not None:
        try:
            await app_state.engine.dispose()
        except Exception:  # noqa: BLE001, S110
            pass
    sync_state()


@asynccontextmanager
async def lifespan(application: Any) -> AsyncIterator[None]:
    await startup()
    try:
        yield
    finally:
        await shutdown()
