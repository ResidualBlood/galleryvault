import json
import logging
import time
from typing import Any

import httpx

from ..config import Settings, get_settings
from ..logging import log_extra
from .messages import (
    archive_batch_result,
    archive_fail,
    archive_ok,
    archive_start,
    archive_summary,
    download_fail,
    download_ok,
    download_summary,
    download_updated,
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
                timeout=httpx.Timeout(45.0), proxy=self.settings.socks5_proxy or self.settings.http_proxy
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
        self._archive_ok: list[tuple[str, str | None]] = []
        self._archive_fail: list[tuple[str, str | None]] = []
        self._last_archive_event_at: float = 0.0

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
        - ``off``: nothing is sent to Telegram (in-app ring still records).
        """
        from .notifications import notify_download

        notify_download(kind, title, detail)
        token = self.settings.telegram_bot_token
        if not token or self.settings.telegram_notify_level == "off":
            return
        if kind == "updated":
            if self.settings.telegram_notify_level == "failures_only":
                return
            old_gid, new_gid = (detail or ":").split(":", 1) if detail and ":" in detail else ("", "")
            text = download_updated(old_gid, new_gid, title, self.message_lang)
            await self.send_message(text)
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

    @property
    def pending_archive_events(self) -> bool:
        """Whether an archive digest is buffered and waiting to be flushed."""
        return bool(self._archive_ok or self._archive_fail)

    def archive_events_stale(self, interval: float) -> bool:
        """Whether the buffered archive digest has received no new events for ``interval``."""
        return bool(self._archive_ok or self._archive_fail) and (
            time.monotonic() - self._last_archive_event_at
        ) >= interval

    async def record_archive_outcome(
        self, kind: str, title: str, detail: str | None = None, *, ring: bool = True
    ) -> None:
        """Record a single-gallery archive terminal event (ok or fail).

        Follows telegram_notify_level:
        - off: nothing sent
        - failures_only: only fail sent (immediately)
        - immediate: sent immediately
        - summary: buffered, flushed when idle or cap reached
        """
        if ring:
            from .notifications import notify_archive

            notify_archive(kind, title, detail)
        token = self.settings.telegram_bot_token
        level = getattr(self.settings, "telegram_notify_level", "summary")
        if not token or level == "off":
            return

        is_fail = kind in {"fail", "archive_fail"}
        if level == "failures_only":
            if not is_fail:
                return
            text = archive_fail(title, detail, self.message_lang)
            await self.send_message(text)
            return

        if level == "immediate":
            if is_fail:
                text = archive_fail(title, detail, self.message_lang)
            else:
                text = archive_ok(title, self.message_lang)
            await self.send_message(text)
            return

        # summary mode: buffer into digest
        if is_fail:
            self._archive_fail.append((title, detail))
        else:
            self._archive_ok.append((title, detail))
        self._last_archive_event_at = time.monotonic()
        if len(self._archive_ok) + len(self._archive_fail) >= _BUFFER_CAP:
            await self.flush_archive_summary()

    async def flush_archive_summary(self) -> bool:
        """Send the buffered archive digest and clear it."""
        if not (self._archive_ok or self._archive_fail):
            return False
        ok, fail = self._archive_ok, self._archive_fail
        lang = self.message_lang
        text = archive_summary(ok, fail, lang)
        self._archive_ok.clear()
        self._archive_fail.clear()
        return await self.send_message(text)

    async def record_batch_archive(
        self,
        event: str,
        *,
        total: int = 0,
        done: int = 0,
        skipped: int = 0,
        failed: int = 0,
        error: str | None = None,
    ) -> None:
        """Send Telegram notifications for batch cold archive operations.

        Follows telegram_notify_level:
        - off: nothing sent
        - failures_only: only fail sent (start and clean success suppressed)
        - immediate: start and finish sent immediately
        - summary: finish sent as summary, start suppressed
        """
        token = self.settings.telegram_bot_token
        level = getattr(self.settings, "telegram_notify_level", "summary")
        if not token or level == "off":
            return

        if event in {"start", "archive_start"}:
            if level in {"failures_only", "summary"}:
                return
            text = archive_start(total, self.message_lang)
            await self.send_message(text)
            return

        # Terminal event (ok / fail)
        has_failure = failed > 0 or bool(error)
        if level == "failures_only" and not has_failure:
            return

        text = archive_batch_result(done, skipped, failed, self.message_lang)
        await self.send_message(text)

    def _resolve_targets(
        self, chat_id: str | int | None = None, force: bool = False
    ) -> list[str]:
        allowed = {str(x) for x in self.settings.telegram_chat_ids}
        if chat_id is None:
            return sorted(allowed)
        target = str(chat_id)
        if not force and target not in allowed:
            logger.warning("Telegram notification skipped: chat is not allowed")
            return []
        return [target]

    def _get_client(self, call_timeout: httpx.Timeout) -> tuple[httpx.AsyncClient, bool]:
        if self.client is not None:
            return self.client, True
        return (
            httpx.AsyncClient(
                timeout=call_timeout,
                proxy=self.settings.socks5_proxy or self.settings.http_proxy,
            ),
            False,
        )

    async def send_message(
        self,
        text: str,
        chat_id: str | int | None = None,
        force: bool = False,
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        token = self.settings.telegram_bot_token
        if not token:
            logger.debug("Telegram notification skipped: not configured")
            return False
        targets = self._resolve_targets(chat_id=chat_id, force=force)
        if not targets:
            logger.warning("Telegram notification skipped: no chat IDs configured")
            return False
        call_timeout = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)
        client, shared = self._get_client(call_timeout)
        try:
            sent = False
            for target in targets:
                payload: dict[str, Any] = {
                    "chat_id": target,
                    "text": text,
                    "parse_mode": "HTML",
                }
                if reply_markup is not None:
                    payload["reply_markup"] = reply_markup
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=payload,
                    timeout=call_timeout,
                )
                response.raise_for_status()
                sent = True
            return sent
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning(
                "Telegram notification failed",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Telegram notification unexpected error",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
            return False
        finally:
            if not shared and client is not None:
                await client.aclose()

    async def send_photo(
        self,
        photo: str | bytes,
        caption: str | None = None,
        chat_id: str | int | None = None,
        force: bool = False,
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        token = self.settings.telegram_bot_token
        if not token:
            logger.debug("Telegram notification skipped: not configured")
            return False
        targets = self._resolve_targets(chat_id=chat_id, force=force)
        if not targets:
            logger.warning("Telegram notification skipped: no chat IDs configured")
            return False
        call_timeout = httpx.Timeout(connect=3.0, read=15.0, write=15.0, pool=3.0)
        client, shared = self._get_client(call_timeout)
        try:
            sent = False
            for target in targets:
                if isinstance(photo, bytes):
                    data: dict[str, Any] = {
                        "chat_id": str(target),
                    }
                    if caption:
                        data["caption"] = caption
                        data["parse_mode"] = "HTML"
                    if reply_markup is not None:
                        data["reply_markup"] = json.dumps(reply_markup)
                    files = {"photo": ("photo.jpg", photo, "image/jpeg")}
                    response = await client.post(
                        f"https://api.telegram.org/bot{token}/sendPhoto",
                        data=data,
                        files=files,
                        timeout=call_timeout,
                    )
                else:
                    payload: dict[str, Any] = {
                        "chat_id": target,
                        "photo": photo,
                    }
                    if caption:
                        payload["caption"] = caption
                        payload["parse_mode"] = "HTML"
                    if reply_markup is not None:
                        payload["reply_markup"] = reply_markup
                    response = await client.post(
                        f"https://api.telegram.org/bot{token}/sendPhoto",
                        json=payload,
                        timeout=call_timeout,
                    )
                response.raise_for_status()
                sent = True
            return sent
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning(
                "Telegram send_photo failed",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Telegram send_photo unexpected error",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
            return False
        finally:
            if not shared and client is not None:
                await client.aclose()

    async def edit_message_text(
        self,
        text: str,
        chat_id: str | int | None = None,
        message_id: int | None = None,
        inline_message_id: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        force: bool = False,
    ) -> bool:
        token = self.settings.telegram_bot_token
        if not token:
            return False
        call_timeout = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)
        client, shared = self._get_client(call_timeout)
        try:
            if inline_message_id:
                payload: dict[str, Any] = {
                    "inline_message_id": inline_message_id,
                    "text": text,
                    "parse_mode": "HTML",
                }
                if reply_markup is not None:
                    payload["reply_markup"] = reply_markup
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/editMessageText",
                    json=payload,
                    timeout=call_timeout,
                )
                response.raise_for_status()
                return True

            targets = self._resolve_targets(chat_id=chat_id, force=force)
            if not targets or message_id is None:
                return False
            sent = False
            for target in targets:
                payload = {
                    "chat_id": target,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "HTML",
                }
                if reply_markup is not None:
                    payload["reply_markup"] = reply_markup
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/editMessageText",
                    json=payload,
                    timeout=call_timeout,
                )
                response.raise_for_status()
                sent = True
            return sent
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning(
                "Telegram edit_message_text failed",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Telegram edit_message_text unexpected error",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
            return False
        finally:
            if not shared and client is not None:
                await client.aclose()

    async def edit_message_reply_markup(
        self,
        chat_id: str | int | None = None,
        message_id: int | None = None,
        inline_message_id: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        force: bool = False,
    ) -> bool:
        token = self.settings.telegram_bot_token
        if not token:
            return False
        call_timeout = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)
        client, shared = self._get_client(call_timeout)
        try:
            if inline_message_id:
                payload: dict[str, Any] = {
                    "inline_message_id": inline_message_id,
                }
                if reply_markup is not None:
                    payload["reply_markup"] = reply_markup
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/editMessageReplyMarkup",
                    json=payload,
                    timeout=call_timeout,
                )
                response.raise_for_status()
                return True

            targets = self._resolve_targets(chat_id=chat_id, force=force)
            if not targets or message_id is None:
                return False
            sent = False
            for target in targets:
                payload = {
                    "chat_id": target,
                    "message_id": message_id,
                }
                if reply_markup is not None:
                    payload["reply_markup"] = reply_markup
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/editMessageReplyMarkup",
                    json=payload,
                    timeout=call_timeout,
                )
                response.raise_for_status()
                sent = True
            return sent
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning(
                "Telegram edit_message_reply_markup failed",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Telegram edit_message_reply_markup unexpected error",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
            return False
        finally:
            if not shared and client is not None:
                await client.aclose()

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
        url: str | None = None,
        cache_time: int | None = None,
    ) -> bool:
        token = self.settings.telegram_bot_token
        if not token or not callback_query_id:
            return False
        call_timeout = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)
        client, shared = self._get_client(call_timeout)
        try:
            payload: dict[str, Any] = {
                "callback_query_id": str(callback_query_id),
                "show_alert": show_alert,
            }
            if text:
                payload["text"] = text
            if url:
                payload["url"] = url
            if cache_time is not None:
                payload["cache_time"] = cache_time
            response = await client.post(
                f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                json=payload,
                timeout=call_timeout,
            )
            response.raise_for_status()
            return True
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning(
                "Telegram answer_callback_query failed",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Telegram answer_callback_query unexpected error",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )
            return False
        finally:
            if not shared and client is not None:
                await client.aclose()


TelegramService = TelegramNotifier
