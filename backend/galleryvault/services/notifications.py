from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any

from ..app.state import app_state

RING_MAX = 100
_COOKIE_STATES = frozenset({"not_logged_in", "no_exhentai_access"})


def _ring() -> deque[dict[str, Any]]:
    extra = app_state.extra
    ring = extra.get("notifications")
    if not isinstance(ring, deque):
        ring = deque(maxlen=RING_MAX)
        extra["notifications"] = ring
        extra["notifications_seq"] = int(extra.get("notifications_seq") or 0)
    return ring


def reset_notifications() -> None:
    extra = app_state.extra
    extra["notifications"] = deque(maxlen=RING_MAX)
    extra["notifications_seq"] = 0
    extra.pop("notifications_cookie_state", None)


def push_notification(
    kind: str, title: str, detail: str | None = None
) -> dict[str, Any]:
    extra = app_state.extra
    seq = int(extra.get("notifications_seq") or 0) + 1
    extra["notifications_seq"] = seq
    item = {
        "id": seq,
        "kind": kind,
        "title": title,
        "detail": detail or "",
        "created_at": datetime.now(UTC).isoformat(),
        "read": False,
    }
    _ring().append(item)
    return item


def list_notifications() -> dict[str, Any]:
    items = list(_ring())
    items.reverse()
    unread = sum(1 for item in items if not item.get("read"))
    return {"items": items, "unread_count": unread}


def mark_notifications_read() -> dict[str, Any]:
    for item in _ring():
        item["read"] = True
    return list_notifications()


def _notify_lang() -> str:
    settings = app_state.settings
    lang = getattr(settings, "telegram_notify_lang", None) if settings else None
    return lang if lang == "en" else "zh"


def notify_download(kind: str, title: str, detail: str | None = None) -> None:
    mapping = {"ok": "download_ok", "fail": "download_fail", "updated": "download_updated"}
    push_notification(mapping.get(kind, f"download_{kind}"), title, detail)


def notify_scan(
    success: bool, *, new: int = 0, removed: int = 0, error: str = ""
) -> None:
    zh = _notify_lang() != "en"
    if success:
        title = "扫库完成" if zh else "Library scan complete"
        push_notification("scan_ok", title, f"+{new} / -{removed}")
        return
    title = "扫库失败" if zh else "Library scan failed"
    push_notification("scan_fail", title, error)


def notify_cookie_health(state: str | None, detail: str | None = None) -> None:
    extra = app_state.extra
    if state not in _COOKIE_STATES:
        extra["notifications_cookie_state"] = state
        return
    if extra.get("notifications_cookie_state") == state:
        return
    extra["notifications_cookie_state"] = state
    zh = _notify_lang() != "en"
    title = "ExHentai Cookie 已失效" if zh else "ExHentai cookie expired"
    push_notification("cookie", title, detail or state)
