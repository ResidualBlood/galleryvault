"""Notifications endpoints, plus the Telegram connectivity probe.

``telegram_test`` moved here from ``tags``; ``tags`` includes
``telegram_router`` at the original registration position and re-exports the
handler so the URL, response codes and exceptions stay unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...services import messages
from ...services.notifications import (
    clear_notifications,
    list_notifications,
    mark_notifications_read,
)
from ..dependencies import get_current_settings
from ..state import app_state

router = APIRouter()
# Included by ``tags`` where ``POST /api/telegram/test`` used to be defined.
telegram_router = APIRouter()


@router.get("/api/notifications")
async def get_notifications() -> dict[str, object]:
    return list_notifications()


@router.post("/api/notifications/read")
async def read_notifications() -> dict[str, object]:
    return mark_notifications_read()


@router.post("/api/notifications/clear")
async def clear_notifications_endpoint() -> dict[str, object]:
    return clear_notifications()


@telegram_router.post("/api/telegram/test")
async def telegram_test() -> dict[str, object]:
    notifier = app_state.telegram
    settings = get_current_settings()
    if notifier is None or not settings.telegram_bot_token:
        raise HTTPException(status_code=422, detail="Telegram bot token is not configured")
    targets = settings.telegram_chat_ids
    if not targets:
        raise HTTPException(status_code=422, detail="No Telegram chat IDs configured")
    results: dict[str, object] = {}
    message = messages.test_message(settings.telegram_notify_lang)
    for chat_id in targets:
        results[str(chat_id)] = await notifier.send_message(message, chat_id=chat_id)
    ok = all(results.values())
    return {"ok": ok, "results": results}
