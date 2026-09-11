"""Bot context encapsulating update payloads, session, and messaging conveniences."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ...config import Settings
    from ..telegram import TelegramNotifier


@dataclass
class BotContext:
    update: dict[str, Any]
    notifier: TelegramNotifier
    settings: Settings
    queue: Any
    chat_id: int | str | None = None
    user_id: int | None = None
    username: str | None = None
    message_id: int | None = None
    text: str = ""
    callback_query_id: str | None = None
    callback_data: str | None = None
    command: str | None = None
    args: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_update(
        cls,
        update: dict[str, Any],
        notifier: TelegramNotifier,
        settings: Settings,
        queue: Any,
    ) -> BotContext:
        """Construct a BotContext from a raw Telegram Update dict."""
        callback_query = update.get("callback_query")
        if callback_query:
            cb_id = str(callback_query.get("id") or "")
            cb_data = str(callback_query.get("data") or "")
            user = callback_query.get("from") or {}
            msg = callback_query.get("message") or {}
            chat = msg.get("chat") or {}
            chat_id = chat.get("id") or user.get("id")
            message_id = msg.get("message_id")
            return cls(
                update=update,
                notifier=notifier,
                settings=settings,
                queue=queue,
                chat_id=chat_id,
                user_id=user.get("id"),
                username=user.get("username"),
                message_id=message_id,
                text=cb_data,
                callback_query_id=cb_id,
                callback_data=cb_data,
            )

        message = update.get("message") or {}
        user = message.get("from") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        message_id = message.get("message_id")
        raw_text = str(message.get("text") or "").strip()

        command: str | None = None
        args = ""
        if raw_text.startswith("/"):
            parts = raw_text.split(None, 1)
            cmd_token = parts[0]
            if "@" in cmd_token:
                cmd_token = cmd_token.split("@", 1)[0]
            command = cmd_token.lower()
            args = parts[1].strip() if len(parts) > 1 else ""

        return cls(
            update=update,
            notifier=notifier,
            settings=settings,
            queue=queue,
            chat_id=chat_id,
            user_id=user.get("id"),
            username=user.get("username"),
            message_id=message_id,
            text=raw_text,
            command=command,
            args=args,
        )

    @property
    def is_callback_query(self) -> bool:
        return bool(self.callback_query_id)

    @property
    def lang(self) -> str:
        """Telegram notification language normalized."""
        if self.settings and getattr(self.settings, "telegram_notify_lang", None):
            return str(self.settings.telegram_notify_lang)
        return getattr(self.notifier, "message_lang", "zh")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Context manager yielding a SQLAlchemy async session from app_state."""
        from ...app.state import app_state

        if not app_state.session_factory:
            raise RuntimeError("Database session factory is not configured in app_state")
        async with app_state.session_factory() as sess:
            yield sess

    async def reply_text(
        self,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        """Send a text reply to the current chat."""
        if self.chat_id is None:
            return False
        kwargs: dict[str, Any] = {"force": True}
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        try:
            return await self.notifier.send_message(text, self.chat_id, **kwargs)
        except TypeError:
            # Fallback for mock notifiers in tests with varying signatures
            kwargs.pop("reply_markup", None)
            try:
                return await self.notifier.send_message(text, self.chat_id, **kwargs)
            except TypeError:
                return await self.notifier.send_message(text, self.chat_id)

    async def reply_photo(
        self,
        photo: str | bytes,
        caption: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        """Send a photo reply to the current chat."""
        if self.chat_id is None or not hasattr(self.notifier, "send_photo"):
            return False
        return await self.notifier.send_photo(
            photo=photo,
            caption=caption,
            chat_id=self.chat_id,
            force=True,
            reply_markup=reply_markup,
        )

    async def edit_text(
        self,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        """Edit the current message text and reply markup."""
        if (
            self.chat_id is None
            or self.message_id is None
            or not hasattr(self.notifier, "edit_message_text")
        ):
            return False
        return await self.notifier.edit_message_text(
            text=text,
            chat_id=self.chat_id,
            message_id=self.message_id,
            reply_markup=reply_markup,
            force=True,
        )

    async def edit_reply_markup(
        self,
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        """Edit the current message reply markup."""
        if (
            self.chat_id is None
            or self.message_id is None
            or not hasattr(self.notifier, "edit_message_reply_markup")
        ):
            return False
        return await self.notifier.edit_message_reply_markup(
            chat_id=self.chat_id,
            message_id=self.message_id,
            reply_markup=reply_markup,
            force=True,
        )

    async def answer_callback(
        self,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool:
        """Answer the incoming callback query if present."""
        if not self.callback_query_id or not hasattr(self.notifier, "answer_callback_query"):
            return False
        return await self.notifier.answer_callback_query(
            callback_query_id=self.callback_query_id,
            text=text,
            show_alert=show_alert,
        )
