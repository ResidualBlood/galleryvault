from __future__ import annotations

import json
import logging
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..app.state import app_state

logger = logging.getLogger(__name__)

RING_MAX = 100
_COOKIE_STATES = frozenset({"not_logged_in", "no_exhentai_access"})


def notifications_path() -> Path | None:
    settings = app_state.settings
    cache_dir = getattr(settings, "thumbnail_cache_dir", None) if settings else None
    if not cache_dir:
        return None
    return Path(cache_dir).parent / "notifications.json"


def _ring() -> deque[dict[str, Any]]:
    extra = app_state.extra
    ring = extra.get("notifications")
    if not isinstance(ring, deque):
        ring = deque(maxlen=RING_MAX)
        extra["notifications"] = ring
        extra["notifications_seq"] = int(extra.get("notifications_seq") or 0)
    return ring


def persist_notifications() -> None:
    path = notifications_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "seq": int(app_state.extra.get("notifications_seq") or 0),
            "items": list(_ring()),
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("notifications persist failed", extra={"error": str(exc)})


def load_notifications() -> None:
    path = notifications_path()
    extra = app_state.extra
    ring = deque(maxlen=RING_MAX)
    seq = 0
    if path is not None and path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw.get("items") if isinstance(raw, dict) else raw
            if isinstance(items, list):
                for item in items[-RING_MAX:]:
                    if isinstance(item, dict):
                        ring.append(item)
                        try:
                            seq = max(seq, int(item.get("id") or 0))
                        except (TypeError, ValueError):
                            pass
            if isinstance(raw, dict):
                try:
                    seq = max(seq, int(raw.get("seq") or 0))
                except (TypeError, ValueError):
                    pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("notifications load failed", extra={"error": str(exc)})
            ring = deque(maxlen=RING_MAX)
            seq = 0
    extra["notifications"] = ring
    extra["notifications_seq"] = seq


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
    persist_notifications()
    return item


def list_notifications() -> dict[str, Any]:
    items = list(_ring())
    items.reverse()
    unread = sum(1 for item in items if not item.get("read"))
    return {"items": items, "unread_count": unread}


def mark_notifications_read() -> dict[str, Any]:
    for item in _ring():
        item["read"] = True
    persist_notifications()
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
