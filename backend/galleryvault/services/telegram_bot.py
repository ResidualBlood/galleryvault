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
from ..services.messages import (
    bot_already_local,
    bot_cancel_not_found,
    bot_cancel_ok,
    bot_cancel_usage,
    bot_gone,
    bot_help,
    bot_paused,
    bot_queue,
    bot_queued,
    bot_queued_updated,
    bot_resumed,
    bot_stats,
    bot_status,
)

logger = logging.getLogger(__name__)

_QUEUE_STATUSES = ("pending", "downloading", "failed")
_CANCELABLE_STATUSES = frozenset({"pending", "downloading"})
_QUEUE_LIST_CAP = 25


async def list_queue_snapshot() -> tuple[list[dict[str, object]], dict[str, int]]:
    from sqlalchemy import func, select

    from ..app.state import app_state
    from ..db.models import DownloadTask

    counts = {"pending": 0, "downloading": 0, "failed": 0}
    if not app_state.session_factory:
        return [], counts
    async with app_state.session_factory() as session:
        count_rows = (
            await session.execute(
                select(DownloadTask.status, func.count())
                .where(DownloadTask.status.in_(_QUEUE_STATUSES))
                .group_by(DownloadTask.status)
            )
        ).all()
        for status, n in count_rows:
            if status in counts:
                counts[status] = int(n or 0)
        rows = (
            await session.scalars(
                select(DownloadTask)
                .where(DownloadTask.status.in_(_QUEUE_STATUSES))
                .order_by(DownloadTask.id.desc())
                .limit(_QUEUE_LIST_CAP)
            )
        ).all()
        items = [
            {
                "id": row.id,
                "gid": row.gid,
                "status": row.status,
                "title": (row.title or "")[:80],
            }
            for row in rows
        ]
        return items, counts


async def library_count() -> int:
    from sqlalchemy import func, select

    from ..app.state import app_state
    from ..db.models import Gallery

    if not app_state.session_factory:
        return 0
    async with app_state.session_factory() as session:
        value = await session.scalar(
            select(func.count())
            .select_from(Gallery)
            .where(Gallery.expunged.is_(False), Gallery.trashed.is_(False))
        )
    return int(value or 0)


async def cancel_download_ident(ident: int) -> tuple[str, int | None, int | None]:
    from sqlalchemy import select

    from ..app.state import app_state
    from ..db.models import DownloadTask
    from ..db.repository import DownloadRepository
    from ..services.download_worker import mark_download_cancelled

    if not app_state.session_factory:
        return "not_found", None, None
    async with app_state.session_factory() as session, session.begin():
        task = await session.get(DownloadTask, ident)
        if task is not None:
            if task.status not in _CANCELABLE_STATUSES:
                return "not_found", None, None
        else:
            found = (
                await session.scalars(
                    select(DownloadTask)
                    .where(
                        DownloadTask.gid == ident,
                        DownloadTask.status.in_(tuple(_CANCELABLE_STATUSES)),
                    )
                    .order_by(DownloadTask.id.desc())
                    .limit(1)
                )
            ).all()
            task = found[0] if found else None
        if task is None or task.status not in _CANCELABLE_STATUSES:
            return "not_found", None, None
        task_id = int(task.id)
        gid = int(task.gid)
        was_downloading = task.status == "downloading"
        if not await DownloadRepository(session).cancel(task_id):
            return "not_found", None, None
    if was_downloading:
        mark_download_cancelled(task_id)
    return "cancelled", task_id, gid


@dataclass(frozen=True)
class TelegramGalleryItem:
    gid: int
    token: str
    title: str
    title_jpn: str | None = None


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
        if not text:
            return
        # Global pause is the SSOT (persisted in settings); self.paused mirrors it for compat
        from ..app.state import app_state
        from ..config import get_settings
        from ..db.repository import SettingsRepository
        from ..services.settings_service import update_runtime_settings

        def _is_global_paused() -> bool:
            s = app_state.settings
            return bool(s and getattr(s, "global_paused", False))

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
                        existing = await SettingsRepository(session).get()
                        merged = {**existing, "global_paused": value}
                        await SettingsRepository(session).save(merged)
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
        elif text == "/help" or text.startswith("/help "):
            await self.notifier.send_message(bot_help(lang), chat_id, force=True)
        elif text == "/queue" or text.startswith("/queue "):
            items, counts = await list_queue_snapshot()
            await self.notifier.send_message(bot_queue(items, counts, lang), chat_id, force=True)
        elif text == "/stats" or text.startswith("/stats "):
            _items, counts = await list_queue_snapshot()
            galleries = await library_count()
            await self.notifier.send_message(
                bot_stats(
                    galleries,
                    counts.get("pending", 0),
                    counts.get("downloading", 0),
                    counts.get("failed", 0),
                    lang,
                ),
                chat_id,
                force=True,
            )
        elif text == "/cancel" or text.startswith("/cancel "):
            parts = text.split(None, 1)
            if len(parts) < 2:
                await self.notifier.send_message(bot_cancel_usage(lang), chat_id, force=True)
                return
            try:
                ident = int(parts[1].strip())
            except ValueError:
                await self.notifier.send_message(
                    bot_cancel_not_found(parts[1].strip(), lang), chat_id, force=True
                )
                return
            status, task_id, gid = await cancel_download_ident(ident)
            if status != "cancelled" or task_id is None:
                await self.notifier.send_message(
                    bot_cancel_not_found(ident, lang), chat_id, force=True
                )
            else:
                await self.notifier.send_message(
                    bot_cancel_ok(task_id, gid if gid is not None else ident, lang),
                    chat_id,
                    force=True,
                )
        else:
            try:
                gid, token = parse_gallery_url(text, self.settings.exhentai_base_url)
            except (ValueError, TypeError):
                await self.notifier.send_message(bot_help(lang), chat_id, force=True)
                return
            self.paused = _is_global_paused()
            if not self.paused:
                from ..app.dependencies import resolve_display_title
                from ..services.download_prepare import prepare_galleries

                try:
                    prepared = (await prepare_galleries([(gid, token)]))[0]
                except Exception:  # noqa: BLE001
                    prepared = None
                if prepared is not None and prepared.gone:
                    label = (
                        resolve_display_title(prepared.title, prepared.title_jpn)
                        or prepared.title
                        or str(gid)
                    )
                    await self.notifier.send_message(bot_gone(label, lang), chat_id, force=True)
                    return
                if prepared is not None and prepared.already_local:
                    label = (
                        resolve_display_title(prepared.title, prepared.title_jpn)
                        or prepared.title
                        or str(prepared.gid)
                    )
                    await self.notifier.send_message(
                        bot_already_local(prepared.gid, label, lang), chat_id, force=True
                    )
                    return
                item_gid, item_token, item_title, item_jpn, old_gid = gid, token, text, None, None
                if prepared is not None:
                    item_gid = prepared.gid
                    item_token = prepared.token
                    item_jpn = prepared.title_jpn
                    old_gid = prepared.old_gid
                    item_title = (
                        resolve_display_title(prepared.title, prepared.title_jpn)
                        or prepared.title
                        or str(prepared.gid)
                    )
                await self.queue.enqueue(
                    TelegramGalleryItem(
                        gid=item_gid, token=item_token, title=item_title, title_jpn=item_jpn
                    )
                )
                if old_gid:
                    await self.notifier.send_message(
                        bot_queued_updated(old_gid, item_gid, item_title, lang),
                        chat_id,
                        force=True,
                    )
                else:
                    await self.notifier.send_message(
                        bot_queued(item_gid, lang, title=item_title), chat_id, force=True
                    )

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
