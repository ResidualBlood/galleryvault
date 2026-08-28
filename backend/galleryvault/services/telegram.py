import logging
import time

import httpx

from ..config import Settings, get_settings
from ..logging import log_extra
from .messages import (
    download_fail,
    download_ok,
    download_summary,
    normalize_lang,
)

logger = logging.getLogger(__name__)

_BUFFER_CAP = 50


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
        # Buffered download outcomes as ``(title, detail)`` pairs so the digest
        # is rendered with the *current* language at flush time (a language
        # switch mid-buffer never leaks stale wording into a summary).
        self._ok: list[tuple[str, str | None]] = []
        self._fail: list[tuple[str, str | None]] = []
        self._last_event_at: float = 0.0

    @property
    def message_lang(self) -> str:
        """Language used for Telegram notification copy (``telegram_notify_lang``)."""
        return normalize_lang(getattr(self.settings, "telegram_notify_lang", "zh"))

    async def aclose(self) -> None:
        if self._owned and self.client is not None:
            await self.client.aclose()

    @property
    def pending_events(self) -> bool:
        """Whether a download digest is buffered and waiting to be flushed."""
        return bool(self._ok or self._fail)

    def events_stale(self, interval: float) -> bool:
        """Whether the buffered digest has received no new events for ``interval``."""
        return bool(self._ok or self._fail) and (
            time.monotonic() - self._last_event_at
        ) >= interval

    async def record_download_outcome(
        self, kind: str, title: str, detail: str | None = None
    ) -> None:
        """Record a download terminal event for Telegram.

        ``kind`` is ``"ok"`` or ``"fail"``. Behaviour follows
        ``telegram_notify_level``:

        - ``immediate``: send right away (old per-event behaviour);
        - ``summary`` (default): buffer into a digest, flushed by the caller
          when the download queue is idle (plus a timer and buffer cap);
        - ``failures_only``: only failures are sent, immediately;
        - ``off``: nothing is sent.
        """
        token = self.settings.telegram_bot_token
        if not token or self.settings.telegram_notify_level == "off":
            return
        if kind == "ok":
            if self.settings.telegram_notify_level == "failures_only":
                return
            self._ok.append((title, detail))
            immediate = self.settings.telegram_notify_level == "immediate"
        else:
            self._fail.append((title, detail))
            immediate = self.settings.telegram_notify_level in {"immediate", "failures_only"}
        if not immediate:
            self._last_event_at = time.monotonic()
        if immediate or len(self._ok) + len(self._fail) >= _BUFFER_CAP:
            await self.flush_summary()

    async def flush_summary(self) -> bool:
        """Send the buffered download digest and clear it."""
        if not (self._ok or self._fail):
            return False
        ok, fail = self._ok, self._fail
        lang = self.message_lang
        if len(ok) == 1 and len(fail) == 0:
            text = download_ok(*ok[0], lang)
        elif len(ok) == 0 and len(fail) == 1:
            text = download_fail(*fail[0], lang)
        else:
            text = download_summary(ok, fail, lang)
        self._ok.clear()
        self._fail.clear()
        return await self.send_message(text)

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
                    json={
                        "chat_id": target,
                        "text": text,
                        "parse_mode": "HTML",
                    },
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
