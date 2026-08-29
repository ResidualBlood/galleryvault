"""Optional Telegram long-polling control plane.

This module deliberately accepts an injected HTTP client so tests never contact Telegram.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..config import Settings
from ..services.eh_client import parse_gallery_url
from ..services.messages import bot_paused, bot_queued, bot_resumed, bot_status

logger = logging.getLogger(__name__)


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
        if text == "/pause":
            self.paused = True
            await self.notifier.send_message(bot_paused(lang), chat_id, force=True)
        elif text == "/resume":
            self.paused = False
            await self.notifier.send_message(bot_resumed(lang), chat_id, force=True)
        elif text == "/status":
            await self.notifier.send_message(bot_status(self.paused, lang), chat_id, force=True)
        else:
            try:
                gid, token = parse_gallery_url(text, self.settings.exhentai_base_url)
            except (ValueError, TypeError):
                return
            if not self.paused:
                await self.queue.enqueue(
                    type("TelegramGallery", (), {"gid": gid, "token": token, "title": text})()
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
