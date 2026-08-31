"""Service for managing, encrypting, decrypting, and refreshing application settings."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..app.state import app_state
from ..config import get_settings, library_root_warnings
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

logger = logging.getLogger(__name__)


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
    current = app_state.settings or get_settings()
    updated = current.model_copy(update=filtered)
    app_state.settings = updated
    from ..app import main
    if hasattr(main, "app") and hasattr(main.app, "state"):
        main.app.state.settings = updated


def start_telegram_bot() -> None:
    task = app_state.extra.get("telegram_bot_task")
    if task is not None and isinstance(task, asyncio.Task):
        task.cancel()
    settings = app_state.settings or get_settings()
    if settings.telegram_bot_token and app_state.telegram is not None:
        from ..app.dependencies import spawn_task

        new_task = spawn_task(
            TelegramBotService(
                settings,
                client=app_state.telegram.client,
                queue=FavoriteDownloadQueue(),
                notifier=app_state.telegram,
            ).run(),
            "telegram bot",
        )
        if new_task is not None:
            app_state.extra["telegram_bot_task"] = new_task


async def refresh_services() -> None:
    """Rebuild network-bound services so changed proxy/cookies apply immediately."""
    settings = app_state.settings or get_settings()
    old_client = app_state.eh_client
    old_telegram = app_state.telegram
    if old_telegram is not None:
        await old_telegram.flush_summary()
        await old_telegram.aclose()
    if old_client is not None:
        await old_client.aclose()

    client = EhClient(settings, max_concurrency=settings.exhentai_max_concurrency)
    app_state.eh_client = client
    app_state.downloader = Downloader(
        client,
        settings.download_root,
        concurrency=settings.download_concurrency,
        page_concurrency=settings.page_concurrency,
    )
    app_state.telegram = TelegramNotifier(settings)
    start_telegram_bot()
    app_state.favorites_service = FavoritesService(
        client, FavoritesRepositoryProxy(), FavoriteDownloadQueue(), app_state.telegram
    )


def settings_public() -> dict[str, Any]:
    current = app_state.settings or get_settings()
    auth_hash_configured = bool(current.auth_password_hash or current.auth_password)
    must_change_password = bool(
        current.auth_required and (not auth_hash_configured or current.auth_password == "p1a2s3s4")
    )
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
