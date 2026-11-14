"""INV-DL-2: download retry/cancel conflicts must surface as real 409s.

Covers the three defects fixed in batch 28:
- retrying a task whose gid already has an active task must not become a 503;
- an IntegrityError (constraint conflict) maps to 409, not "Database is unavailable";
- cancelling a finished task returns 409 carrying the real status;
- Telegram ``/retry all`` uses ``DownloadRepository.retry_all`` instead of
  re-implementing the reset loop (which had no gid de-duplication).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Self

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from galleryvault.app.dependencies import db_error
from galleryvault.app.routers import downloads as downloads_router
from galleryvault.app.state import app_state
from galleryvault.db.repositories.downloads import DownloadRepository
from galleryvault.services.messages import bot_retry_all_ok
from galleryvault.services.tgbot.context import BotContext
from galleryvault.services.tgbot.handlers import queue as queue_handler


class _Task:
    def __init__(self, *, task_id: int = 10, gid: int = 777, status: str = "failed") -> None:
        self.id = task_id
        self.gid = gid
        self.status = status
        self.retry_count = 3
        self.retry_at = object()
        self.error_message = "boom"
        self.finished_at = object()
        self.max_retries = 0


class _RetrySession:
    def __init__(self, row: _Task, active_id: int | None = None) -> None:
        self.row = row
        self.active_id = active_id
        self.scalar_calls = 0

    async def get(self, model: object, pk: int) -> _Task:
        return self.row

    async def scalar(self, stmt: object) -> int | None:
        self.scalar_calls += 1
        return self.active_id


class _RepoSession:
    def __init__(self, row: _Task | None) -> None:
        self.row = row

    async def get(self, model: object, pk: int) -> _Task | None:
        return self.row


@pytest.mark.asyncio
async def test_retry_active_gid_returns_409() -> None:
    """Same gid already active -> 409, and the row stays untouched."""
    row = _Task(status="failed")
    session = _RetrySession(row, active_id=99)

    with pytest.raises(HTTPException) as excinfo:
        await downloads_router.retry_download(10, session=session)

    assert excinfo.value.status_code == 409
    assert "active download already exists" in str(excinfo.value.detail)
    assert session.scalar_calls == 1
    assert row.status == "failed"


@pytest.mark.asyncio
async def test_retry_without_active_gid_still_succeeds() -> None:
    row = _Task(status="success")
    session = _RetrySession(row, active_id=None)

    result = await downloads_router.retry_download(10, session=session)

    assert result == {"id": 10, "status": "pending"}
    assert row.status == "pending"
    assert row.max_retries == 10
    assert row.retry_count == 0


@pytest.mark.asyncio
async def test_cancel_finished_returns_409_with_real_status() -> None:
    row = _Task(status="success")

    class _FakeRepo:
        def __init__(self, session: object) -> None:
            pass

        async def cancel(self, task_id: int) -> str:
            return row.status

    original = downloads_router.DownloadRepository
    downloads_router.DownloadRepository = _FakeRepo
    try:
        with pytest.raises(HTTPException) as excinfo:
            await downloads_router.cancel_download(10, session=_RepoSession(row))
    finally:
        downloads_router.DownloadRepository = original

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == {"status": "success", "message": "task already finished"}
    assert row.status == "success"


@pytest.mark.asyncio
async def test_cancel_active_task_still_cancels() -> None:
    row = _Task(status="pending")

    class _FakeRepo:
        def __init__(self, session: object) -> None:
            pass

        async def cancel(self, task_id: int) -> str:
            row.status = "cancelled"
            return row.status

    original = downloads_router.DownloadRepository
    downloads_router.DownloadRepository = _FakeRepo
    try:
        result = await downloads_router.cancel_download(10, session=_RepoSession(row))
    finally:
        downloads_router.DownloadRepository = original
        app_state.task_manager.clear_cancelled(10)

    assert result == {"id": 10, "status": "cancelled"}
    assert row.status == "cancelled"


@pytest.mark.asyncio
async def test_repository_cancel_returns_real_terminal_status() -> None:
    finished = _Task(status="failed")
    repo = DownloadRepository(_RepoSession(finished))
    assert await repo.cancel(10) == "failed"
    assert finished.status == "failed"

    active = _Task(status="downloading")
    repo = DownloadRepository(_RepoSession(active))
    assert await repo.cancel(10) == "cancelled"
    assert active.status == "cancelled"

    repo = DownloadRepository(_RepoSession(None))
    assert await repo.cancel(10) is None


def test_db_error_maps_integrity_error_to_409() -> None:
    conflict = db_error(IntegrityError("INSERT", {}, Exception("duplicate key")))
    assert conflict.status_code == 409
    assert conflict.detail == "Conflict"

    outage = db_error(SQLAlchemyError("connection lost"))
    assert outage.status_code == 503
    assert outage.detail == "Database is unavailable"


@pytest.mark.asyncio
async def test_telegram_retry_all_uses_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    cleared: list[int] = []

    class _FakeRepo:
        def __init__(self, session: object) -> None:
            pass

        async def retry_all(self) -> list[int]:
            calls.append("retry_all")
            return [11, 12]

    class _FakeSession:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> bool:
            return False

    class _Notifier:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def send_message(self, text: str, chat_id: object, **kwargs: object) -> bool:
            self.calls.append(text)
            return True

    notifier = _Notifier()
    ctx = BotContext(
        update={},
        notifier=notifier,
        settings=SimpleNamespace(telegram_notify_lang="zh"),
        queue=None,
        chat_id=1,
        args="all",
    )
    monkeypatch.setattr(queue_handler, "DownloadRepository", _FakeRepo)
    monkeypatch.setattr(queue_handler, "clear_download_cancelled", cleared.append)
    original_factory = app_state.session_factory
    app_state.session_factory = lambda: _FakeSession()
    try:
        await queue_handler.cmd_retry(ctx)
    finally:
        app_state.session_factory = original_factory

    assert calls == ["retry_all"]
    assert cleared == [11, 12]
    assert notifier.calls == [bot_retry_all_ok(2, lang="zh")]
