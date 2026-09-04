import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from galleryvault.app.routers import notifications as notif_router
from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services.notifications import (
    clear_notifications,
    list_notifications,
    load_notifications,
    mark_notifications_read,
    notify_cookie_health,
    persist_notifications,
    push_notification,
    reset_notifications,
)
from galleryvault.services.telegram import TelegramNotifier


def setup_function() -> None:
    reset_notifications()


def test_notification_ring_write_read_and_cap() -> None:
    first = push_notification("download_ok", "A", "1")
    push_notification("download_fail", "B", "err")
    data = list_notifications()
    assert data["unread_count"] == 2
    assert [item["title"] for item in data["items"]] == ["B", "A"]
    assert data["items"][1]["id"] == first["id"]
    marked = mark_notifications_read()
    assert marked["unread_count"] == 0
    assert all(item["read"] for item in marked["items"])
    for i in range(120):
        push_notification("scan_ok", str(i), "")
    data = list_notifications()
    assert len(data["items"]) == 100
    titles = [item["title"] for item in data["items"]]
    assert "119" in titles
    assert "0" not in titles


def test_cookie_health_dedupes_same_state() -> None:
    orig = app_state.settings
    app_state.settings = Settings(telegram_notify_lang="en")
    try:
        notify_cookie_health("not_logged_in", "x")
        notify_cookie_health("not_logged_in", "x")
        data = list_notifications()
        assert data["unread_count"] == 1
        assert data["items"][0]["kind"] == "cookie"
        assert data["items"][0]["title"] == "ExHentai cookie expired"
        notify_cookie_health("no_exhentai_access", "y")
        data = list_notifications()
        assert data["unread_count"] == 2
        assert data["items"][0]["kind"] == "cookie_no_access"
        assert data["items"][0]["title"] == "No ExHentai access"
        assert "expired" not in data["items"][0]["title"].lower()
        notify_cookie_health("ok", None)
        assert list_notifications()["unread_count"] == 2
        notify_cookie_health("not_logged_in", "again")
        data = list_notifications()
        assert data["unread_count"] == 3
        assert data["items"][0]["kind"] == "cookie"
    finally:
        app_state.settings = orig


def test_cookie_health_no_access_title_zh() -> None:
    orig = app_state.settings
    app_state.settings = Settings(telegram_notify_lang="zh")
    try:
        notify_cookie_health("no_exhentai_access", "detail_zh")
        data = list_notifications()
        assert data["unread_count"] == 1
        assert data["items"][0]["kind"] == "cookie_no_access"
        assert data["items"][0]["title"] == "ExHentai 无里站访问权限"
        assert "失效" not in data["items"][0]["title"]
    finally:
        app_state.settings = orig


async def test_download_outcome_off_still_rings() -> None:
    off_settings = Settings(
        telegram_bot_token="secret",
        telegram_chat_ids=["7"],
        telegram_notify_level="off",
    )
    notifier = TelegramNotifier(off_settings)
    await notifier.record_download_outcome("fail", "B", "Timeout")
    assert not notifier.pending_events
    data = list_notifications()
    assert data["unread_count"] == 1
    assert data["items"][0]["kind"] == "download_fail"
    assert data["items"][0]["title"] == "B"


def test_notifications_persist_and_restore(tmp_path, monkeypatch) -> None:
    from galleryvault.app.state import app_state
    from galleryvault.config import Settings

    orig = app_state.settings
    cache = tmp_path / "thumbs"
    cache.mkdir()
    app_state.settings = Settings(thumbnail_cache_dir=str(cache))
    try:
        reset_notifications()
        push_notification("scan_ok", "persisted", "x")
        persist_notifications()
        path = tmp_path / "notifications.json"
        assert path.is_file()
        reset_notifications()
        assert list_notifications()["items"] == []
        load_notifications()
        data = list_notifications()
        assert data["unread_count"] == 1
        assert data["items"][0]["title"] == "persisted"
    finally:
        app_state.settings = orig


def test_clear_notifications() -> None:
    push_notification("scan_ok", "item1", "detail")
    push_notification("scan_fail", "item2", "detail2")
    assert list_notifications()["unread_count"] == 2
    res = clear_notifications()
    assert res == {"items": [], "unread_count": 0}
    assert list_notifications() == {"items": [], "unread_count": 0}


def test_clear_notifications_persists_empty(tmp_path) -> None:
    orig = app_state.settings
    cache = tmp_path / "thumbs"
    cache.mkdir()
    app_state.settings = Settings(thumbnail_cache_dir=str(cache))
    try:
        reset_notifications()
        push_notification("scan_ok", "persisted", "x")
        path = tmp_path / "notifications.json"
        assert path.is_file()
        res = clear_notifications()
        assert res == {"items": [], "unread_count": 0}
        assert json.loads(path.read_text(encoding="utf-8"))["items"] == []
        load_notifications()
        assert list_notifications() == {"items": [], "unread_count": 0}
    finally:
        app_state.settings = orig


def test_clear_notifications_endpoint() -> None:
    app = FastAPI()
    app.include_router(notif_router.router)
    client = TestClient(app)

    push_notification("scan_ok", "test", "")
    assert client.get("/api/notifications").json()["unread_count"] == 1

    resp = client.post("/api/notifications/clear")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "unread_count": 0}
    assert client.get("/api/notifications").json() == {"items": [], "unread_count": 0}

