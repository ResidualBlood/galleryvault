from types import SimpleNamespace

import httpx
import pytest

from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services.telegram_bot import (
    TelegramBotService,
    TelegramGalleryItem,
    cancel_download_ident,
)


class _Notifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, bool]] = []
        self.photo_calls: list[dict] = []
        self.edit_calls: list[dict] = []
        self.cb_answers: list[dict] = []

    async def send_message(self, text, chat_id=None, force=False, **kwargs):
        self.calls.append((text, chat_id, force))
        return True

    async def send_photo(self, photo, caption=None, chat_id=None, force=False, reply_markup=None):
        self.photo_calls.append({
            "photo": photo,
            "caption": caption,
            "chat_id": chat_id,
            "reply_markup": reply_markup,
        })
        return True

    async def edit_message_text(self, text, chat_id=None, message_id=None, reply_markup=None, force=False):
        self.edit_calls.append({
            "text": text,
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": reply_markup,
        })
        return True

    async def edit_message_reply_markup(self, chat_id=None, message_id=None, reply_markup=None, force=False):
        return True

    async def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        self.cb_answers.append({"id": callback_query_id, "text": text, "show_alert": show_alert})
        return True


class _Queue:
    def __init__(self) -> None:
        self.items: list[TelegramGalleryItem] = []

    async def enqueue(self, item):
        self.items.append(item)
        return True


def _bot(_monkeypatch=None, *, paused: bool = False):
    settings = Settings(
        telegram_bot_token="secret",
        telegram_allowed_user_ids=[7],
        telegram_notify_lang="en",
        exhentai_base_url="https://exhentai.org",
    )
    orig = app_state.settings
    app_state.settings = settings.model_copy(update={"global_paused": paused})
    notifier = _Notifier()
    queue = _Queue()
    bot = TelegramBotService(settings, client=None, queue=queue, notifier=notifier)
    return bot, notifier, queue, orig


async def _update(bot, text: str) -> None:
    await bot.handle_update(
        {"message": {"from": {"id": 7}, "text": text, "chat": {"id": 7}}}
    )


async def _callback_update(bot, data: str, message_id: int = 100) -> None:
    await bot.handle_update(
        {
            "callback_query": {
                "id": "cb123",
                "from": {"id": 7, "username": "tester"},
                "message": {"message_id": message_id, "chat": {"id": 7}},
                "data": data,
            }
        }
    )


@pytest.mark.asyncio
async def test_help_lists_commands() -> None:
    bot, notifier, _queue, orig = _bot(None)
    try:
        await _update(bot, "/help")
        assert len(notifier.calls) == 1
        text, chat_id, force = notifier.calls[0]
        assert force is True
        assert chat_id == 7
        for cmd in ("/pause", "/resume", "/status", "/help", "/queue", "/cancel", "/stats"):
            assert cmd in text
        assert "URL" in text
    finally:
        app_state.settings = orig


@pytest.mark.asyncio
async def test_unknown_text_replies_help() -> None:
    bot, notifier, queue, orig = _bot()
    try:
        await _update(bot, "hello there")
        assert queue.items == []
        assert len(notifier.calls) == 1
        text, _chat, force = notifier.calls[0]
        assert force is True
        assert "/help" in text
    finally:
        app_state.settings = orig


@pytest.mark.asyncio
async def test_stats_summarizes_library_and_queue(monkeypatch) -> None:
    from galleryvault.services import telegram_bot as bot_mod

    async def fake_snapshot():
        return ([], {"pending": 2, "downloading": 1, "failed": 3})

    async def fake_count():
        return 42

    monkeypatch.setattr(bot_mod, "list_queue_snapshot", fake_snapshot)
    monkeypatch.setattr(bot_mod, "library_count", fake_count)
    bot, notifier, _queue, orig = _bot()
    try:
        await _update(bot, "/stats")
        text, _chat, force = notifier.calls[0]
        assert force is True
        assert "42" in text
        assert "2" in text and "1" in text and "3" in text
    finally:
        app_state.settings = orig


@pytest.mark.asyncio
async def test_queue_uses_snapshot(monkeypatch) -> None:
    from galleryvault.services import telegram_bot as bot_mod

    async def fake_snapshot():
        return (
            [{"id": 3, "gid": 99, "status": "pending", "title": "Demo"}],
            {"pending": 1, "downloading": 0, "failed": 2},
        )

    monkeypatch.setattr(bot_mod, "list_queue_snapshot", fake_snapshot)
    bot, notifier, _queue, orig = _bot()
    try:
        await _update(bot, "/queue")
        text, _chat, force = notifier.calls[0]
        assert force is True
        assert "pending" in text.lower() or "1" in text
        assert "99" in text
        assert "Demo" in text
    finally:
        app_state.settings = orig


@pytest.mark.asyncio
async def test_cancel_by_id_and_missing(monkeypatch) -> None:
    from galleryvault.services import telegram_bot as bot_mod

    async def fake_cancel(ident: int):
        if ident == 5:
            return "cancelled", 5, 111
        return "not_found", None, None

    monkeypatch.setattr(bot_mod, "cancel_download_ident", fake_cancel)
    bot, notifier, _queue, orig = _bot()
    try:
        await _update(bot, "/cancel")
        assert "Usage" in notifier.calls[-1][0]
        assert notifier.calls[-1][2] is True
        await _update(bot, "/cancel 5")
        assert "Cancelled" in notifier.calls[-1][0]
        assert "5" in notifier.calls[-1][0]
        await _update(bot, "/cancel 9")
        assert "not found" in notifier.calls[-1][0].lower()
        await _update(bot, "/cancel nope")
        assert "not found" in notifier.calls[-1][0].lower()
    finally:
        app_state.settings = orig


@pytest.mark.asyncio
async def test_paste_url_enqueues(monkeypatch) -> None:
    async def boom(_items):
        raise RuntimeError("no network")

    monkeypatch.setattr(
        "galleryvault.services.download_prepare.prepare_galleries", boom
    )
    bot, notifier, queue, orig = _bot()
    try:
        await _update(bot, "https://exhentai.org/g/12345/abcdef/")
        assert len(queue.items) == 1
        assert queue.items[0].gid == 12345
        assert notifier.calls[-1][2] is True
        assert "12345" in notifier.calls[-1][0]

        await _update(bot, "https://exhentai.org/g/67890/fedcba")
        assert len(queue.items) == 2
        assert queue.items[1].gid == 67890
        assert notifier.calls[-1][2] is True
        assert "67890" in notifier.calls[-1][0]
    finally:
        app_state.settings = orig


@pytest.mark.asyncio
async def test_disallowed_user_is_ignored() -> None:
    bot, notifier, queue, orig = _bot()
    try:
        await bot.handle_update(
            {"message": {"from": {"id": 99}, "text": "/help", "chat": {"id": 99}}}
        )
        assert notifier.calls == []
        assert queue.items == []
    finally:
        app_state.settings = orig


@pytest.mark.asyncio
async def test_poll_once_uses_injected_client() -> None:
    settings = Settings(
        telegram_bot_token="secret", telegram_allowed_user_ids=[7], telegram_notify_lang="en"
    )
    orig = app_state.settings
    app_state.settings = settings.model_copy(update={"global_paused": False})
    notifier = _Notifier()
    queue = _Queue()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"ok": True, "result": []})

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            bot = TelegramBotService(settings, client=client, queue=queue, notifier=notifier)
            assert await bot.poll_once() == 0
        assert calls and "getUpdates" in calls[0]
        assert notifier.calls == []
    finally:
        app_state.settings = orig


def _dl_task(task_id: int, gid: int, status: str) -> SimpleNamespace:
    return SimpleNamespace(id=task_id, gid=gid, status=status)


class _CancelSession:
    def __init__(self, tasks: list[SimpleNamespace]) -> None:
        self._tasks = list(tasks)
        self._missed_ident: int | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def begin(self):
        return self

    async def get(self, _model, pk):
        for row in self._tasks:
            if row.id == pk:
                return row
        self._missed_ident = pk
        return None

    async def scalars(self, _stmt):
        ident = self._missed_ident
        rows = [
            row
            for row in self._tasks
            if row.gid == ident and row.status in {"pending", "downloading"}
        ]
        rows.sort(key=lambda row: row.id, reverse=True)
        return SimpleNamespace(all=lambda: rows[:1])


async def _run_cancel(tasks: list[SimpleNamespace], ident: int, monkeypatch):
    marked: list[int] = []
    orig_factory = app_state.session_factory
    session = _CancelSession(tasks)
    monkeypatch.setattr(
        "galleryvault.services.download_worker.mark_download_cancelled",
        marked.append,
    )
    app_state.session_factory = lambda: session
    try:
        result = await cancel_download_ident(ident)
        return result, marked, tasks
    finally:
        app_state.session_factory = orig_factory


@pytest.mark.asyncio
async def test_cancel_download_ident_pending_by_id(monkeypatch) -> None:
    task = _dl_task(5, 111, "pending")
    result, marked, _tasks = await _run_cancel([task], 5, monkeypatch)
    assert result == ("cancelled", 5, 111)
    assert task.status == "cancelled"
    assert marked == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "success", "cancelled"])
async def test_cancel_download_ident_terminal_by_id_not_found(status, monkeypatch) -> None:
    task = _dl_task(5, 111, status)
    result, marked, _tasks = await _run_cancel([task], 5, monkeypatch)
    assert result == ("not_found", None, None)
    assert task.status == status
    assert marked == []


@pytest.mark.asyncio
async def test_cancel_download_ident_gid_hits_downloading(monkeypatch) -> None:
    older = _dl_task(1, 999, "success")
    active = _dl_task(8, 999, "downloading")
    result, marked, _tasks = await _run_cancel([older, active], 999, monkeypatch)
    assert result == ("cancelled", 8, 999)
    assert active.status == "cancelled"
    assert older.status == "success"
    assert marked == [8]


@pytest.mark.asyncio
async def test_cancel_download_ident_gid_only_success_not_found(monkeypatch) -> None:
    task = _dl_task(10, 999, "success")
    result, marked, _tasks = await _run_cancel([task], 999, monkeypatch)
    assert result == ("not_found", None, None)
    assert task.status == "success"
    assert marked == []


@pytest.mark.asyncio
async def test_admin_commands(monkeypatch) -> None:
    from galleryvault.services.tgbot import get_root_router

    bot, notifier, _queue, orig = _bot()
    bot.router = get_root_router()
    orig_factory = app_state.session_factory
    app_state.session_factory = None
    try:
        # /ping
        await _update(bot, "/ping")
        assert any("Pong" in c[0] for c in notifier.calls)

        # /status
        await _update(bot, "/status")
        assert any("系统" in c[0] or "System" in c[0] or "running" in c[0].lower() for c in notifier.calls)

        # /cookie
        async def fake_cookie():
            return {"state": "valid", "detail": None, "checked_at": "2026-09-11"}

        monkeypatch.setattr("galleryvault.services.eh_client.probe_cookie_health", fake_cookie)
        await _update(bot, "/cookie")
        assert any("cookie" in c[0].lower() for c in notifier.calls)

        # /quota
        async def fake_quota():
            return {"image_limit": {"current": 50, "limit": 1000}, "gp": 5000}

        monkeypatch.setattr("galleryvault.app.routers.tasks.get_quota", fake_quota)
        await _update(bot, "/quota")
        assert any("配额" in c[0] or "Quota" in c[0] or "50" in c[0] for c in notifier.calls)

        # /storage
        await _update(bot, "/storage")
        assert any("存储" in c[0] or "Storage" in c[0] or "图库" in c[0] for c in notifier.calls)

        # /scan
        await _update(bot, "/scan")
        assert any("扫描" in c[0] or "scan" in c[0].lower() for c in notifier.calls)
    finally:
        app_state.settings = orig
        app_state.session_factory = orig_factory


@pytest.mark.asyncio
async def test_queue_extended_and_callbacks(monkeypatch) -> None:
    from galleryvault.services.tgbot import get_root_router

    bot, notifier, _queue, orig = _bot()
    bot.router = get_root_router()
    orig_factory = app_state.session_factory
    app_state.session_factory = None
    try:
        # /retry usage
        await _update(bot, "/retry")
        assert any("用法" in c[0] or "Usage" in c[0] for c in notifier.calls)

        # /retry all (without db)
        await _update(bot, "/retry all")
        assert any("Database" in c[0] or "数据库" in c[0] for c in notifier.calls)

        # /clear (without db)
        await _update(bot, "/clear")
        assert any("Database" in c[0] or "数据库" in c[0] for c in notifier.calls)

        # mock snapshot for callbacks
        async def fake_snapshot():
            return ([], {"pending": 0, "downloading": 0, "failed": 0})

        monkeypatch.setattr("galleryvault.services.tgbot.handlers.queue.list_queue_snapshot", fake_snapshot)

        # callback queue:refresh
        await _callback_update(bot, "queue:refresh")
        assert len(notifier.edit_calls) >= 1
        assert len(notifier.cb_answers) >= 1

        # callback queue:clear
        await _callback_update(bot, "queue:clear")
        assert len(notifier.edit_calls) >= 2

        # callback queue:retry_all
        await _callback_update(bot, "queue:retry_all")
        assert len(notifier.edit_calls) >= 3
    finally:
        app_state.settings = orig
        app_state.session_factory = orig_factory


@pytest.mark.asyncio
async def test_tasks_extended_and_callbacks(monkeypatch) -> None:
    from galleryvault.services.tgbot import get_root_router

    bot, notifier, _queue, orig = _bot()
    bot.router = get_root_router()
    try:
        class FakeTaskManager:
            def get_running_summary(self):
                return [{"task": "scan", "status": "running", "done": 10, "total": 100, "started_at": "12:00"}]

        monkeypatch.setattr("galleryvault.services.tgbot.handlers.tasks.get_task_manager", FakeTaskManager)

        async def fake_cancel_bg(task_name):
            return {"task": task_name, "status": "cancelling"}

        monkeypatch.setattr("galleryvault.services.tgbot.handlers.tasks.cancel_background_task", fake_cancel_bg)

        # /tasks
        await _update(bot, "/tasks")
        assert any("scan" in c[0] for c in notifier.calls)

        # /kill usage
        await _update(bot, "/kill")
        assert any("用法" in c[0] or "Usage" in c[0] for c in notifier.calls)

        # /kill with name
        await _update(bot, "/kill fake_task")
        assert any("fake_task" in c[0] for c in notifier.calls)

        # callback tasks:refresh
        await _callback_update(bot, "tasks:refresh")
        assert len(notifier.edit_calls) >= 1

        # callback tasks:kill:scan
        await _callback_update(bot, "tasks:kill:scan")
        assert len(notifier.edit_calls) >= 2
    finally:
        app_state.settings = orig


@pytest.mark.asyncio
async def test_library_commands_and_callbacks(monkeypatch) -> None:
    from galleryvault.services.tgbot import get_root_router

    bot, notifier, _queue, orig = _bot()
    bot.router = get_root_router()
    orig_factory = app_state.session_factory
    app_state.session_factory = None
    try:
        # /search without query
        await _update(bot, "/search")
        assert any("用法" in c[0] or "Usage" in c[0] for c in notifier.calls)

        # /search with query (db not configured fallback)
        await _update(bot, "/search touhou")
        assert any("数据库" in c[0] or "未就绪" in c[0] for c in notifier.calls)

        # /info without gid
        await _update(bot, "/info")
        assert any("用法" in c[0] or "Usage" in c[0] for c in notifier.calls)

        # /info with gid
        await _update(bot, "/info 123456")
        assert any("数据库" in c[0] or "未就绪" in c[0] for c in notifier.calls)

        # /random
        await _update(bot, "/random")
        assert any("数据库" in c[0] or "未就绪" in c[0] for c in notifier.calls)

        # /redownload without gid
        await _update(bot, "/redownload")
        assert any("用法" in c[0] or "Usage" in c[0] for c in notifier.calls)

        # /redownload with gid
        await _update(bot, "/redownload 999999")
        assert any("数据库" in c[0] or "未就绪" in c[0] for c in notifier.calls)

        # callback lib:p:test:p:2
        await _callback_update(bot, "lib:p:test:p:2")
        assert len(notifier.cb_answers) >= 1

        # callback lib:info:123456
        await _callback_update(bot, "lib:info:123456")
        assert len(notifier.cb_answers) >= 2

        # callback lib:random
        await _callback_update(bot, "lib:random")
        assert len(notifier.cb_answers) >= 3

        # callback lib:redownload:123456
        await _callback_update(bot, "lib:redownload:123456")
        assert len(notifier.cb_answers) >= 4

        # callback lib:noop
        await _callback_update(bot, "lib:noop")
        assert len(notifier.cb_answers) >= 5
    finally:
        app_state.settings = orig
        app_state.session_factory = orig_factory


@pytest.mark.asyncio
async def test_favorites_commands(monkeypatch) -> None:
    from galleryvault.services.tgbot import get_root_router

    bot, notifier, _queue, orig = _bot()
    bot.router = get_root_router()
    try:
        # /fav_sync without cookies
        await _update(bot, "/fav_sync")
        assert any("Cookie" in c[0] for c in notifier.calls)

        # /fav_download with invalid arg
        await _update(bot, "/fav_download abc")
        assert any("用法" in c[0] or "0 到 9" in c[0] for c in notifier.calls)

        # /fav_download valid
        await _update(bot, "/fav_download 2")
        assert any("触发" in c[0] or "分类 2" in c[0] for c in notifier.calls)

        # /fav_download all
        await _update(bot, "/fav_download")
        assert any("触发" in c[0] or "全部分类" in c[0] for c in notifier.calls)

        # /fav_check
        await _update(bot, "/fav_check")
        assert any("收藏夹" in c[0] or "检查" in c[0] for c in notifier.calls)
    finally:
        app_state.settings = orig


@pytest.mark.asyncio
async def test_comprehensive_help_coverage() -> None:
    from galleryvault.services.tgbot import get_root_router

    bot, notifier, _queue, orig = _bot()
    bot.router = get_root_router()
    try:
        await _update(bot, "/help")
        assert len(notifier.calls) == 1
        text = notifier.calls[0][0]
        # Core original commands
        for cmd in ("/pause", "/resume", "/status", "/help", "/queue", "/cancel", "/stats"):
            assert cmd in text
        # New admin / queue / task commands
        for cmd in ("/ping", "/cookie", "/quota", "/storage", "/scan", "/retry", "/clear", "/tasks", "/kill"):
            assert cmd in text
        # New library / favorites commands
        for cmd in ("/search", "/info", "/random", "/redownload", "/fav_sync", "/fav_download", "/fav_check"):
            assert cmd in text
    finally:
        app_state.settings = orig
