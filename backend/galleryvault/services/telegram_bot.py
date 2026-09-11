"""Optional Telegram long-polling control plane.

This module deliberately accepts an injected HTTP client so tests never contact Telegram.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..logging import log_extra
from .tgbot.context import BotContext
from .tgbot.router import CommandRouter

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
    def __init__(
        self,
        settings: Settings,
        *,
        client: Any,
        queue: Any,
        notifier: Any,
        router: CommandRouter | None = None,
    ) -> None:
        self.settings, self.client, self.queue, self.notifier = settings, client, queue, notifier
        self.offset = 0
        self.paused = False
        self.router = router or self._build_default_router()

    def _allowed(self, update: dict) -> bool:
        user_id = None
        if msg := update.get("message"):
            user_id = msg.get("from", {}).get("id")
        elif cb := update.get("callback_query"):
            user_id = cb.get("from", {}).get("id")
        return bool(self.settings.telegram_allowed_user_ids) and int(user_id or 0) in {
            int(item) for item in self.settings.telegram_allowed_user_ids
        }

    def _build_default_router(self) -> CommandRouter:
        # Import at call time so telegram_bot can finish loading first.
        # Module-level import of tgbot/__init__ would circular-import this class.
        from .tgbot import get_root_router

        return get_root_router()

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
        ctx = BotContext.from_update(
            update=update,
            notifier=self.notifier,
            settings=self.settings,
            queue=self.queue,
        )
        if not ctx.text and not ctx.is_callback_query:
            return
        await self.router.dispatch(ctx)

    async def run(self) -> None:
        try:
            commands: list[dict[str, str]] = []
            seen: set[str] = set()
            for name, (_func, desc) in getattr(self.router, "_commands", {}).items():
                cmd_name = name.lstrip("/").strip().lower()
                clean_desc = (desc or "").strip()
                if cmd_name and clean_desc and cmd_name not in seen:
                    seen.add(cmd_name)
                    commands.append({"command": cmd_name, "description": clean_desc})
            if commands and hasattr(self.notifier, "set_my_commands"):
                await self.notifier.set_my_commands(commands)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Telegram bot command registration failed",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
            )

        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Telegram bot polling failed",
                    extra=log_extra(error=type(exc).__name__),
                    exc_info=True,
                )
                await asyncio.sleep(2)
