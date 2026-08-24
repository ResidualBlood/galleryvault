import logging

import httpx

from ..config import Settings, get_settings
from ..logging import log_extra

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(
        self, settings: Settings | None = None, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self._owned = client is None and bool(self.settings.telegram_bot_token)
        self.client = client or (
            httpx.AsyncClient(
                timeout=15, proxy=self.settings.socks5_proxy or self.settings.http_proxy
            )
            if self._owned
            else None
        )

    async def aclose(self) -> None:
        if self._owned and self.client is not None:
            await self.client.aclose()

    async def send_message(self, text: str, chat_id: str | int | None = None) -> bool:
        token, allowed = (
            self.settings.telegram_bot_token,
            {str(x) for x in self.settings.telegram_chat_ids},
        )
        target = str(chat_id) if chat_id is not None else None
        if not token:
            logger.debug("Telegram notification skipped: not configured")
            return False
        if target is None or target not in allowed:
            logger.warning("Telegram notification skipped: chat is not allowed")
            return False
        client = self.client or httpx.AsyncClient(
            timeout=15, proxy=self.settings.socks5_proxy or self.settings.http_proxy
        )
        try:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": target, "text": text},
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning(
                "Telegram notification failed", extra=log_extra(error=type(exc).__name__)
            )
            return False
        finally:
            if self._owned:
                await client.aclose()


TelegramService = TelegramNotifier
