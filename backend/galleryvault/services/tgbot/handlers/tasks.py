"""Background long-running tasks inspection and control (/tasks, /kill)."""

from __future__ import annotations

from typing import Any

from galleryvault.app.dependencies import get_task_manager
from galleryvault.app.routers.tasks import cancel_background_task
from galleryvault.services.messages import (
    bot_kill_result,
    bot_kill_usage,
    bot_tasks_list,
)
from galleryvault.services.tgbot.context import BotContext
from galleryvault.services.tgbot.keyboards import inline_button, inline_keyboard
from galleryvault.services.tgbot.router import CommandRouter

router = CommandRouter()


def _build_tasks_keyboard(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Build inline buttons to allow quick cancellation of running tasks."""
    buttons = [inline_button("🔄 刷新任务", callback_data="tasks:refresh")]
    for item in tasks[:4]:
        task_name = str(item.get("task") or "")
        if task_name:
            buttons.append(
                inline_button(f"🛑 中断 {task_name}", callback_data=f"tasks:kill:{task_name}")
            )
    return inline_keyboard([buttons[i : i + 2] for i in range(0, len(buttons), 2)])


@router.command(["tasks"], description="List running background tasks")
async def cmd_tasks(ctx: BotContext) -> None:
    """List all currently active long-running background tasks."""
    tm = get_task_manager()
    running = tm.get_running_summary()
    text = bot_tasks_list(running, lang=ctx.lang)
    kb = _build_tasks_keyboard(running)
    await ctx.reply_text(text, reply_markup=kb)


@router.command(["kill"], description="Interrupt background task: /kill <task_name>")
async def cmd_kill(ctx: BotContext) -> None:
    """Interrupt a running background task by name."""
    task_name = ctx.args.strip()
    if not task_name:
        await ctx.reply_text(bot_kill_usage(ctx.lang))
        return

    try:
        res = await cancel_background_task(task_name)
        await ctx.reply_text(
            bot_kill_result(
                res.get("task", task_name),
                status=str(res.get("status", "cancelling")),
                lang=ctx.lang,
            )
        )
    except Exception as exc:  # noqa: BLE001
        await ctx.reply_text(f"❌ Cancel task failed: {exc}")


@router.callback(r"^tasks:(.*)$")
async def cb_tasks(ctx: BotContext) -> None:
    """Handle task inline actions (refresh, kill)."""
    match = ctx.extra.get("match")
    action = match.group(1) if match else ""
    await ctx.answer_callback()

    if action == "refresh":
        tm = get_task_manager()
        running = tm.get_running_summary()
        text = bot_tasks_list(running, lang=ctx.lang)
        kb = _build_tasks_keyboard(running)
        await ctx.edit_text(text, reply_markup=kb)

    elif action.startswith("kill:"):
        task_name = action.removeprefix("kill:").strip()
        try:
            await cancel_background_task(task_name)
        except Exception:  # noqa: BLE001, S110
            pass
        tm = get_task_manager()
        running = tm.get_running_summary()
        text = bot_tasks_list(running, lang=ctx.lang)
        kb = _build_tasks_keyboard(running)
        await ctx.edit_text(text, reply_markup=kb)
