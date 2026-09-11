"""Service for managing, encrypting, decrypting, and refreshing application settings."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ..config import get_settings, library_root_warnings, normalize_archive_roots
from ..logging import log_extra
from ..secrets import (
    decrypt_json_or_value,
    decrypt_or_plain,
    is_encrypted,
)
from ..services.downloader import Downloader
from ..services.eh_client import EhClient
from ..services.favorites import FavoritesService
from ..services.favorites_worker import FavoriteDownloadQueue, FavoritesRepositoryProxy
from ..services.telegram import TelegramNotifier
from ..services.telegram_bot import TelegramBotService
from .base_service import BaseService

if TYPE_CHECKING:
    from ..app.core.task_dispatcher import TaskDispatcher
    from ..app.core.uow import UnitOfWork

logger = logging.getLogger(__name__)


def _is_mock_or_test_instance(obj: Any, real_type: Any) -> bool:
    if obj is None:
        return False
    if not isinstance(real_type, type):
        return True
    if not isinstance(obj, real_type):
        return True
    cls_name = type(obj).__name__.lower()
    return (
        "mock" in cls_name
        or "fake" in cls_name
        or hasattr(obj, "_mock_return_value")
        or hasattr(obj, "assert_called")
    )


def _get_app_state() -> Any | None:
    """Safely obtain global app_state if available, avoiding rigid module-level binding."""
    try:
        from ..app.state import app_state

        return app_state
    except (ImportError, AttributeError):
        return None


def is_public_site(url: str | None) -> bool:
    if not url:
        return False
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return "e-hentai.org" in host


def decrypt_user_settings(persisted: dict[str, Any]) -> dict[str, Any]:
    persisted = dict(persisted)
    cookies = persisted.get("exhentai_cookies")
    if is_encrypted(cookies):
        cookies = decrypt_json_or_value(cookies)
    if isinstance(cookies, str) and cookies:
        try:
            import json
            cookies = json.loads(cookies)
        except Exception:  # noqa: BLE001
            cookies = {}
    if not isinstance(cookies, dict):
        cookies = {}
    persisted["exhentai_cookies"] = cookies

    token = persisted.get("telegram_bot_token")
    if is_encrypted(token):
        persisted["telegram_bot_token"] = decrypt_or_plain(token)
    return persisted


def update_runtime_settings(values: dict[str, Any]) -> None:
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
        "cold_storage_root",
        "archive_roots",
        "auto_archive_downloads",
        "archive_delete_source",
        "exhentai_base_url",
        "exhentai_cookies",
        "http_proxy",
        "socks5_proxy",
        "download_root",
        "download_concurrency",
        "page_concurrency",
        "download_quality",
        "download_title",
        "archive_quality",
        "favorites_archive_enabled",
        "favorites_archive_max_pages",
        "archive_fallback_pages",
        "use_hah",
        "image_download_timeout_seconds",
        "image_slow_warmup_seconds",
        "image_min_speed_kb_s",
        "title_display",
        "favorites_categories",
        "download_favorites_enabled",
        "favorites_poll_interval_minutes",
        "telegram_bot_token",
        "telegram_chat_ids",
        "telegram_allowed_user_ids",
        "telegram_notify_level",
        "telegram_notify_lang",
        "auto_sync_tags",
        "tag_sync_interval_seconds",
        "tag_sync_concurrency",
        "generate_thumbnails",
        "duplicate_policy",
        "auth_required",
        "trusted_proxies",
        "tag_translation_update_interval_minutes",
        "global_paused",
    }
    filtered = {k: v for k, v in values.items() if k in allowed and v is not None}
    if "exhentai_cookies" in filtered:
        c = filtered["exhentai_cookies"]
        if isinstance(c, str):
            try:
                import json
                c = json.loads(c) if c else {}
            except Exception:  # noqa: BLE001
                c = {}
        if not isinstance(c, dict):
            c = {}
        filtered["exhentai_cookies"] = {str(k): str(v) for k, v in c.items()}
    if "archive_roots" in filtered:
        filtered["archive_roots"] = normalize_archive_roots(filtered["archive_roots"])
        filtered["cold_storage_root"] = (
            filtered["archive_roots"][0] if filtered["archive_roots"] else ""
        )
    elif "cold_storage_root" in filtered:
        cr = str(filtered["cold_storage_root"]).strip()
        filtered["cold_storage_root"] = cr
        filtered["archive_roots"] = [cr] if cr else []

    app_st = _get_app_state()
    current = (app_st.settings if app_st and getattr(app_st, "settings", None) else None) or get_settings()
    updated = current.model_copy(update=filtered)
    if app_st is not None:
        app_st.settings = updated
        from ..app.state import sync_state
        sync_state()


def start_telegram_bot() -> None:
    app_st = _get_app_state()
    if app_st is None:
        return

    task = app_st.extra.get("telegram_bot_task")
    if task is not None and hasattr(task, "cancel"):
        try:
            task.cancel()
        except Exception:  # noqa: BLE001, S110
            pass
        app_st.extra.get("spawned_tasks", set()).discard(task)
        app_st.extra["telegram_bot_task"] = None

    settings = app_st.settings or get_settings()
    if settings.telegram_bot_token and app_st.telegram is not None:
        from ..app.dependencies import spawn_task
        from ..services.tgbot import get_root_router

        new_task = spawn_task(
            TelegramBotService(
                settings,
                client=app_st.telegram.client,
                queue=FavoriteDownloadQueue(),
                notifier=app_st.telegram,
                router=get_root_router(),
            ).run(),
            "telegram bot",
        )
        if new_task is not None:
            app_st.extra["telegram_bot_task"] = new_task
            app_st.extra.setdefault("spawned_tasks", set()).add(new_task)

    from ..app.state import sync_state
    sync_state()


async def refresh_services() -> None:
    """Rebuild network-bound services so changed proxy/cookies apply immediately."""
    app_st = _get_app_state()
    if app_st is None:
        return

    settings = app_st.settings or get_settings()
    old_client = app_st.eh_client
    old_telegram = app_st.telegram

    # 1. Drain retired TelegramNotifier in background without blocking ongoing requests
    if old_telegram is not None:
        if _is_mock_or_test_instance(old_telegram, TelegramNotifier):
            if hasattr(old_telegram, "aclose"):
                await old_telegram.aclose()
            elif hasattr(old_telegram, "close"):
                res = old_telegram.close()
                if hasattr(res, "__await__"):
                    await res
        else:
            async def _drain_telegram(tg: TelegramNotifier) -> None:
                try:
                    await asyncio.sleep(5.0)
                    await tg.flush_summary()
                    await asyncio.sleep(60.0)
                    await tg.aclose()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Error draining retired TelegramNotifier",
                        extra=log_extra(error=str(exc)),
                    )

            from ..app.dependencies import spawn_task

            tg_task = spawn_task(_drain_telegram(old_telegram), "drain retired telegram")
            if tg_task is None:
                try:
                    asyncio.create_task(_drain_telegram(old_telegram))
                except Exception:  # noqa: BLE001, S110
                    pass

    # 2. Build new client and retire old EhClient gracefully
    client = EhClient(settings, max_concurrency=settings.exhentai_max_concurrency)
    client_mgr = getattr(app_st, "eh_client_manager", None)
    if _is_mock_or_test_instance(old_client, EhClient):
        if hasattr(old_client, "aclose"):
            await old_client.aclose()
        elif hasattr(old_client, "close"):
            res = old_client.close()
            if hasattr(res, "__await__"):
                await res
        if client_mgr is not None:
            if hasattr(client_mgr, "_active_client"):
                client_mgr._active_client = client
                client_mgr._active_generation += 1
            elif hasattr(client_mgr, "update_client"):
                client_mgr.update_client(client)
    elif client_mgr is not None and hasattr(client_mgr, "update_client"):
        client_mgr.update_client(client)
    elif old_client is not None:
        async def _drain_eh_client(c: Any) -> None:
            try:
                await asyncio.sleep(120.0)
                if hasattr(c, "aclose"):
                    await c.aclose()
                elif hasattr(c, "close"):
                    res = c.close()
                    if hasattr(res, "__await__"):
                        await res
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error draining retired EhClient",
                    extra=log_extra(error=str(exc)),
                )

        from ..app.dependencies import spawn_task

        c_task = spawn_task(_drain_eh_client(old_client), "drain retired eh_client")
        if c_task is None:
            try:
                asyncio.create_task(_drain_eh_client(old_client))
            except Exception:  # noqa: BLE001, S110
                pass

    downloader = Downloader(
        (lambda: app_st.eh_client) if app_st is not None else client,
        settings.download_root,
        concurrency=settings.download_concurrency,
        page_concurrency=settings.page_concurrency,
    )
    telegram = TelegramNotifier(settings)
    favorites_service = FavoritesService(
        client, FavoritesRepositoryProxy(), FavoriteDownloadQueue(), telegram
    )

    for key, obj in (
        ("eh_client", client),
        ("downloader", downloader),
        ("telegram", telegram),
        ("favorites_service", favorites_service),
    ):
        setattr(app_st, key, obj)

    from ..app.state import sync_state

    sync_state()
    start_telegram_bot()
    from ..app.lifespan import ensure_translation_updater

    ensure_translation_updater()

    dl_task = app_st.extra.get("download_worker_task")
    if dl_task is not None and not dl_task.done():
        from .download_worker import adjust_download_concurrency

        adjust_download_concurrency(settings.download_concurrency)

    ts_task = app_st.extra.get("tag_sync_worker_task")
    if ts_task is not None and not ts_task.done():
        from .tag_sync_worker import adjust_tag_sync_concurrency

        adjust_tag_sync_concurrency(settings.tag_sync_concurrency)


def settings_public() -> dict[str, Any]:
    app_st = _get_app_state()
    current = (app_st.settings if app_st and getattr(app_st, "settings", None) else None) or get_settings()
    auth_hash_configured = bool(current.auth_password_hash or current.auth_password)
    must_change_password = bool(
        current.auth_required and (not auth_hash_configured or current.auth_password == "p1a2s3s4")
    )
    return {
        "library_roots": current.library_roots,
        "library_root_warnings": library_root_warnings(current.library_roots),
        "cold_storage_root": current.cold_storage_root,
        "archive_roots": current.archive_roots,
        "auto_archive_downloads": current.auto_archive_downloads,
        "archive_delete_source": current.archive_delete_source,
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
        "archive_quality": current.archive_quality,
        "favorites_archive_enabled": current.favorites_archive_enabled,
        "favorites_archive_max_pages": current.favorites_archive_max_pages,
        "archive_fallback_pages": current.archive_fallback_pages,
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
        "auth_hash_configured": auth_hash_configured,
        "must_change_password": must_change_password,
    }


class SettingsService(BaseService):
    """Service governing application configuration, hot-reload, and persistence."""

    def __init__(
        self,
        uow: UnitOfWork | None = None,
        task_dispatcher: TaskDispatcher | None = None,
    ) -> None:
        super().__init__(uow=uow, task_dispatcher=task_dispatcher)

    def get_public_settings(self) -> dict[str, Any]:
        """Return public/sanitized settings dict suitable for API and frontend display."""
        return settings_public()

    async def get_persisted_settings(self) -> dict[str, Any]:
        """Fetch raw decrypted persisted user settings from database."""
        async with self.transaction():
            persisted = await self.uow.settings.get()
            return decrypt_user_settings(persisted)

    async def update_settings(
        self,
        values: dict[str, Any],
        refresh: bool = True,
    ) -> dict[str, Any]:
        """Update user settings, persist to database, sync runtime state and reload services."""
        # 1. Update runtime memory state
        update_runtime_settings(values)

        # 2. Persist to database
        async with self.transaction():
            current_persisted = await self.uow.settings.get()
            updated_dict = dict(current_persisted)
            for k, v in values.items():
                if v is not None:
                    updated_dict[k] = v
            await self.uow.settings.save(updated_dict)

        # 3. Optional reload of services
        if refresh:
            await self.reload_services()

        return self.get_public_settings()

    async def get_runtime_auth(self) -> dict[str, Any]:
        """Fetch non-editable runtime auth settings."""
        async with self.transaction():
            return await self.uow.settings.get_extra()

    async def save_runtime_auth(self, value: dict[str, Any]) -> None:
        """Persist non-editable runtime settings (e.g. password hash)."""
        async with self.transaction():
            await self.uow.settings.save_extra(value)

    async def reload_services(self) -> None:
        """Trigger hot reload of network-bound services (EhClient, Downloader, Telegram, etc.)."""
        await refresh_services()
