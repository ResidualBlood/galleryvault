"""Optional Telegram long-polling control plane.

This module deliberately accepts an injected HTTP client so tests never contact Telegram.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..services.eh_client import parse_gallery_url
from ..services.messages import bot_paused, bot_queued, bot_resumed, bot_status

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramGalleryItem:
    gid: int
    token: str
    title: str


class TelegramBotService:
    def __init__(self, settings: Settings, *, client: Any, queue: Any, notifier: Any) -> None:
        self.settings, self.client, self.queue, self.notifier = settings, client, queue, notifier
        self.offset = 0
        self.paused = False

    def _allowed(self, update: dict) -> bool:
        user = update.get("message", {}).get("from", {}).get("id")
        return bool(self.settings.telegram_allowed_user_ids) and int(user or 0) in {
            int(item) for item in self.settings.telegram_allowed_user_ids
        }

    async def poll_once(self) -> int:
        if not self.settings.telegram_bot_token:
            return 0
        response = await self.client.get(
            f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/getUpdates",
            params={"offset": self.offset, "timeout": 30},
        )
        response.raise_for_status()
        updates = response.json().get("result", [])
        for update in updates:
            self.offset = max(self.offset, int(update.get("update_id", 0)) + 1)
            await self.handle_update(update)
        return len(updates)

    async def handle_update(self, update: dict) -> None:
        if not self._allowed(update):
            return
        message = update.get("message", {})
        text = str(message.get("text", "")).strip()
        chat_id = message.get("chat", {}).get("id")
        lang = self.settings.telegram_notify_lang
        # Global pause is the SSOT (persisted in settings); self.paused mirrors it for compat
        from ..app.state import app_state
        from ..config import get_settings
        from ..db.repository import SettingsRepository
        from ..services.settings_service import update_runtime_settings

        def _is_global_paused() -> bool:
            s = self.settings or app_state.settings or get_settings()
            return bool(getattr(s, "global_paused", False))

        async def _set_global_paused(value: bool) -> None:
            s = self.settings or app_state.settings or get_settings()
            new_s = s.model_copy(update={"global_paused": value})
            # Update both global and instance settings for consistency
            app_state.settings = new_s
            self.settings = new_s
            self.paused = value
            update_runtime_settings({"global_paused": value})
            try:
                if app_state.session_factory:
                    async with app_state.session_factory() as session, session.begin():
                        await SettingsRepository(session).save({"global_paused": value})
            except Exception as exc:  # noqa: BLE001
                logger.warning("global pause persist failed", extra={"error": type(exc).__name__})

        if text == "/pause":
            await _set_global_paused(True)
            await self.notifier.send_message(bot_paused(lang), chat_id, force=True)
        elif text == "/resume":
            await _set_global_paused(False)
            await self.notifier.send_message(bot_resumed(lang), chat_id, force=True)
        elif text == "/status":
            paused = _is_global_paused()
            self.paused = paused
            await self.notifier.send_message(bot_status(paused, lang), chat_id, force=True)
        else:
            try:
                gid, token = parse_gallery_url(text, self.settings.exhentai_base_url)
            except (ValueError, TypeError):
                return
            if not _is_global_paused() and not self.paused:
                await self.queue.enqueue(
                    TelegramGalleryItem(gid=gid, token=token, title=text)
                )
                await self.notifier.send_message(bot_queued(gid, lang), chat_id, force=True)

    async def run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - network errors must not kill the app
                logger.warning(
                    "Telegram bot polling failed", extra={"context": {"error": type(exc).__name__}}
                )
                await asyncio.sleep(2)
