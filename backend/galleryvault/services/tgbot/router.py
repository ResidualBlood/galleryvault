"""Command and Callback Query router for Telegram Bot."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from re import Pattern
from typing import TYPE_CHECKING, Any

from ...logging import log_extra

if TYPE_CHECKING:
    from .context import BotContext

logger = logging.getLogger(__name__)

HandlerFunc = Callable[["BotContext"], Awaitable[Any]]


class CommandRouter:
    """Dispatches Telegram updates to registered command or callback handlers."""

    def __init__(self) -> None:
        self._commands: dict[str, tuple[HandlerFunc, str]] = {}
        self._callbacks: list[tuple[Pattern[str] | str, HandlerFunc]] = []
        self._default_message_handler: HandlerFunc | None = None
        self._default_command_handler: HandlerFunc | None = None
        self._default_callback_handler: HandlerFunc | None = None

    def command(
        self,
        name_or_names: str | list[str],
        description: str = "",
    ) -> Callable[[HandlerFunc], HandlerFunc]:
        """Decorator to register a command handler."""
        names = [name_or_names] if isinstance(name_or_names, str) else name_or_names

        def decorator(func: HandlerFunc) -> HandlerFunc:
            for name in names:
                clean_name = name.strip()
                if not clean_name.startswith("/"):
                    clean_name = f"/{clean_name}"
                clean_name = clean_name.lower()
                self._commands[clean_name] = (func, description)
            return func

        return decorator

    def callback(
        self,
        pattern: str | Pattern[str],
    ) -> Callable[[HandlerFunc], HandlerFunc]:
        """Decorator to register an inline keyboard callback_query handler."""

        def decorator(func: HandlerFunc) -> HandlerFunc:
            self._callbacks.append((pattern, func))
            return func

        return decorator

    def default_message(self, func: HandlerFunc) -> HandlerFunc:
        """Decorator for messages that are not commands (e.g. gallery URLs)."""
        self._default_message_handler = func
        return func

    def default_command(self, func: HandlerFunc) -> HandlerFunc:
        """Decorator for unhandled /commands."""
        self._default_command_handler = func
        return func

    def default_callback(self, func: HandlerFunc) -> HandlerFunc:
        """Decorator for unhandled callback_queries."""
        self._default_callback_handler = func
        return func

    def include_router(self, other: CommandRouter) -> None:
        """Merge another router's registered commands and callbacks into this one."""
        self._commands.update(other._commands)
        self._callbacks.extend(other._callbacks)
        if other._default_message_handler is not None:
            self._default_message_handler = other._default_message_handler
        if other._default_command_handler is not None:
            self._default_command_handler = other._default_command_handler
        if other._default_callback_handler is not None:
            self._default_callback_handler = other._default_callback_handler

    async def dispatch(self, ctx: BotContext) -> bool:
        """Dispatch the BotContext to the matching handler."""
        try:
            if ctx.is_callback_query:
                return await self._dispatch_callback(ctx)
            if ctx.command:
                return await self._dispatch_command(ctx)
            if ctx.text:
                return await self._dispatch_message(ctx)
            return False
        except Exception as exc:
            logger.warning(
                "Error dispatching bot update",
                extra=log_extra(error=type(exc).__name__, message=str(exc)),
                exc_info=True,
            )
            if ctx.is_callback_query:
                from galleryvault.services.messages import bot_text

                await ctx.answer_callback(
                    bot_text(ctx.lang, "bot_dispatch_error"), show_alert=True
                )
            return False

    async def _dispatch_callback(self, ctx: BotContext) -> bool:
        cb_data = ctx.callback_data or ""
        for pattern, handler in self._callbacks:
            matched = False
            if isinstance(pattern, str):
                if cb_data == pattern or cb_data.startswith(f"{pattern}:"):
                    matched = True
                    # If it has a prefix colon, populate match-like group
                    if ":" in cb_data:
                        ctx.extra["prefix_arg"] = cb_data.split(":", 1)[1]
                else:
                    try:
                        m = re.match(pattern, cb_data)
                        if m:
                            matched = True
                            ctx.extra["match"] = m
                    except re.error:
                        pass
            elif isinstance(pattern, re.Pattern):
                m = pattern.match(cb_data)
                if m:
                    matched = True
                    ctx.extra["match"] = m

            if matched:
                await handler(ctx)
                return True

        if self._default_callback_handler is not None:
            await self._default_callback_handler(ctx)
            return True

        # Always acknowledge callback query so client stops spinner
        await ctx.answer_callback()
        return True

    async def _dispatch_command(self, ctx: BotContext) -> bool:
        cmd = (ctx.command or "").lower()
        entry = self._commands.get(cmd)
        if entry is not None:
            handler, _ = entry
            await handler(ctx)
            return True

        if self._default_command_handler is not None:
            await self._default_command_handler(ctx)
            return True

        return False

    async def _dispatch_message(self, ctx: BotContext) -> bool:
        if self._default_message_handler is not None:
            await self._default_message_handler(ctx)
            return True
        return False
