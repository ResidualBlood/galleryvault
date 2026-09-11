"""Download queue control commands and callbacks (/queue, /pause, /resume, /cancel, /retry, /clear)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from galleryvault.app.dependencies import get_settings
from galleryvault.app.lifespan import update_runtime_settings
from galleryvault.app.state import app_state
from galleryvault.db.models import DownloadTask as DownloadTaskModel
from galleryvault.db.repository import DownloadRepository
from galleryvault.db.session import safe_transaction
from galleryvault.logging import log_extra
from galleryvault.services.download_worker import clear_download_cancelled
from galleryvault.services.messages import (
    bot_cancel_not_found,
    bot_cancel_ok,
    bot_cancel_usage,
    bot_clear_success,
    bot_paused,
    bot_queue,
    bot_resumed,
    bot_retry_all_ok,
    bot_retry_not_found,
    bot_retry_ok,
    bot_retry_usage,
    bot_text,
)
from galleryvault.services.telegram_bot import cancel_download_ident, list_queue_snapshot
from galleryvault.services.tgbot.context import BotContext
from galleryvault.services.tgbot.keyboards import inline_button, inline_keyboard
from galleryvault.services.tgbot.router import CommandRouter

router = CommandRouter()
logger = logging.getLogger(__name__)

_MANUAL_RETRY_MAX = 10


def _reset_task_for_retry(task: DownloadTaskModel) -> None:
    """Reset a terminal download task so the worker will claim it again."""
    task.status = "pending"
    task.retry_count = 0
    task.retry_at = None
    task.error_message = None
    task.finished_at = None
    task.max_retries = 10
    clear_download_cancelled(task.id)


async def _set_global_paused(ctx: BotContext, value: bool) -> None:
    """Set and persist global download paused setting."""
    s = ctx.settings or app_state.settings or get_settings()
    new_s = s.model_copy(update={"global_paused": value})
    ctx.settings = new_s
    app_state.settings = new_s
    update_runtime_settings({"global_paused": value})
    try:
        if app_state.session_factory:
            from galleryvault.db.repository import SettingsRepository

            async with app_state.session_factory() as session, session.begin():
                existing = await SettingsRepository(session).get()
                merged = {**existing, "global_paused": value}
                await SettingsRepository(session).save(merged)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "global pause persist failed", extra=log_extra(error=type(exc).__name__)
        )


def _build_queue_keyboard(counts: dict[str, int], lang: str) -> dict[str, Any]:
    """Build inline action buttons for queue inspection."""
    buttons = [
        inline_button(bot_text(lang, "bot_btn_refresh"), callback_data="queue:refresh"),
        inline_button(bot_text(lang, "bot_btn_clear_done"), callback_data="queue:clear"),
    ]
    if (counts.get("failed") or 0) > 0:
        buttons.append(
            inline_button(bot_text(lang, "bot_btn_retry_all"), callback_data="queue:retry_all")
        )
    return inline_keyboard([buttons])


@router.command(["pause"], description="Pause all downloads")
async def cmd_pause(ctx: BotContext) -> None:
    """Pause downloads globally."""
    await _set_global_paused(ctx, True)
    await ctx.reply_text(bot_paused(ctx.lang))


@router.command(["resume"], description="Resume all downloads")
async def cmd_resume(ctx: BotContext) -> None:
    """Resume downloads globally."""
    await _set_global_paused(ctx, False)
    await ctx.reply_text(bot_resumed(ctx.lang))


@router.command(["queue"], description="Show download queue snapshot")
async def cmd_queue(ctx: BotContext) -> None:
    """Show current downloads in progress, pending, and failed."""
    rows, counts = await list_queue_snapshot()
    text = bot_queue(rows, counts, ctx.lang)
    kb = _build_queue_keyboard(counts, ctx.lang)
    await ctx.reply_text(text, reply_markup=kb)


@router.command(["cancel"], description="Cancel download task: /cancel <id|gid>")
async def cmd_cancel(ctx: BotContext) -> None:
    """Cancel a downloading or pending task by task id or gallery id."""
    raw = ctx.args.strip()
    if not raw:
        await ctx.reply_text(bot_cancel_usage(ctx.lang))
        return
    try:
        ident = int(raw)
    except ValueError:
        await ctx.reply_text(bot_cancel_usage(ctx.lang))
        return

    status, task_id, gid = await cancel_download_ident(ident)
    if status == "cancelled" and task_id is not None:
        await ctx.reply_text(bot_cancel_ok(task_id, gid if gid is not None else ident, ctx.lang))
    else:
        await ctx.reply_text(bot_cancel_not_found(ident, ctx.lang))


@router.command(["retry"], description="Retry failed downloads: /retry <id|all>")
async def cmd_retry(ctx: BotContext) -> None:
    """Retry a single failed download or all failed downloads."""
    arg = ctx.args.strip().lower()
    if not arg:
        await ctx.reply_text(bot_retry_usage(ctx.lang))
        return

    if not app_state.session_factory:
        await ctx.reply_text(bot_text(ctx.lang, "bot_db_not_ready"))
        return

    if arg == "all":
        count = 0
        async with app_state.session_factory() as session, safe_transaction(session):
            stmt = select(DownloadTaskModel).where(
                DownloadTaskModel.status.in_(["failed", "cancelled"])
            )
            res = await session.execute(stmt)
            tasks = list(res.scalars().all())
            for t in tasks:
                _reset_task_for_retry(t)
                count += 1
        await ctx.reply_text(bot_retry_all_ok(count, lang=ctx.lang))
        return

    try:
        task_id = int(arg)
    except ValueError:
        await ctx.reply_text(bot_retry_usage(ctx.lang))
        return

    gid: int | None = None
    found = False
    async with app_state.session_factory() as session, safe_transaction(session):
        row = await session.get(DownloadTaskModel, task_id)
        if row and row.status in {"failed", "cancelled", "success"}:
            _reset_task_for_retry(row)
            gid = row.gid
            found = True

    if found:
        await ctx.reply_text(bot_retry_ok(task_id, gid, lang=ctx.lang))
    else:
        await ctx.reply_text(bot_retry_not_found(task_id, lang=ctx.lang))


@router.command(["clear"], description="Clear completed download task history")
async def cmd_clear(ctx: BotContext) -> None:
    """Clear finished download tasks from history."""
    if not app_state.session_factory:
        await ctx.reply_text(bot_text(ctx.lang, "bot_db_not_ready"))
        return
    async with app_state.session_factory() as session, safe_transaction(session):
        deleted = await DownloadRepository(session).delete_success()
    await ctx.reply_text(bot_clear_success(deleted, lang=ctx.lang))


@router.callback(r"^queue:(.*)$")
async def cb_queue(ctx: BotContext) -> None:
    """Handle queue inline keyboard actions (refresh, clear, retry_all)."""
    match = ctx.extra.get("match")
    action = match.group(1) if match else ""
    await ctx.answer_callback()

    if action == "refresh":
        rows, counts = await list_queue_snapshot()
        text = bot_queue(rows, counts, ctx.lang)
        kb = _build_queue_keyboard(counts, ctx.lang)
        await ctx.edit_text(text, reply_markup=kb)

    elif action == "clear":
        if app_state.session_factory:
            async with app_state.session_factory() as session, safe_transaction(session):
                await DownloadRepository(session).delete_success()
        rows, counts = await list_queue_snapshot()
        text = bot_queue(rows, counts, ctx.lang)
        kb = _build_queue_keyboard(counts, ctx.lang)
        await ctx.edit_text(text, reply_markup=kb)

    elif action == "retry_all":
        if app_state.session_factory:
            async with app_state.session_factory() as session, safe_transaction(session):
                stmt = select(DownloadTaskModel).where(
                    DownloadTaskModel.status.in_(["failed", "cancelled"])
                )
                res = await session.execute(stmt)
                for t in res.scalars().all():
                    _reset_task_for_retry(t)
        rows, counts = await list_queue_snapshot()
        text = bot_queue(rows, counts, ctx.lang)
        kb = _build_queue_keyboard(counts, ctx.lang)
        await ctx.edit_text(text, reply_markup=kb)
