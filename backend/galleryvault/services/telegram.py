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

    async def send_message(
        self, text: str, chat_id: str | int | None = None, force: bool = False
    ) -> bool:
        token = self.settings.telegram_bot_token
        if not token:
            logger.debug("Telegram notification skipped: not configured")
            return False
        allowed = {str(x) for x in self.settings.telegram_chat_ids}
        if chat_id is None:
            # Automatic notifications (download success/failure, scan done)
            # fan out to every configured chat instead of being dropped.
            targets = sorted(allowed)
        else:
            target = str(chat_id)
            if not force and target not in allowed:
                logger.warning("Telegram notification skipped: chat is not allowed")
                return False
            targets = [target]
        if not targets:
            logger.warning("Telegram notification skipped: no chat IDs configured")
            return False
        # Reuse the shared client when present (the Telegram bot polls through
        # the same one), otherwise open a short-lived client for this call.
        shared = self.client is not None
        client = self.client or httpx.AsyncClient(
            timeout=15, proxy=self.settings.socks5_proxy or self.settings.http_proxy
        )
        try:
            sent = False
            for target in targets:
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": target, "text": text},
                )
                response.raise_for_status()
                sent = True
            return sent
        except httpx.HTTPError as exc:
            logger.warning(
                "Telegram notification failed", extra=log_extra(error=type(exc).__name__)
            )
            return False
        finally:
            # Never close the shared client (owned by this notifier and shared
            # with the polling bot); only tear down the per-call client.
            if not shared and client is not None:
                await client.aclose()


TelegramService = TelegramNotifier
