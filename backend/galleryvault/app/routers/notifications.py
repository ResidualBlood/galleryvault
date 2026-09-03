from __future__ import annotations

from fastapi import APIRouter

from ...services.notifications import list_notifications, mark_notifications_read

router = APIRouter()


@router.get("/api/notifications")
async def get_notifications() -> dict[str, object]:
    return list_notifications()


@router.post("/api/notifications/read")
async def read_notifications() -> dict[str, object]:
    return mark_notifications_read()
