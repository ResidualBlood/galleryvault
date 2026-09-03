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

    async def send_message(self, text, chat_id=None, force=False):
        self.calls.append((text, chat_id, force))


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


@pytest.mark.asyncio
async def test_help_lists_commands() -> None:
    bot, notifier, _queue, orig = _bot(None)
    try:
        await _update(bot, "/help")
        assert len(notifier.calls) == 1
        text, chat_id, force = notifier.calls[0]
        assert force is True
        assert chat_id == 7
        for cmd in ("/pause", "/resume", "/status", "/help", "/queue", "/cancel"):
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
