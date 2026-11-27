"""Characterisation tests for the download attempt helpers (T9.1b).

The extracted helpers must keep the retry/pause semantics of the inline
``_run_download_inner`` body:

* when over the challenge budget the task is failed, not parked for a retry;
* a cancelled attempt must not consume the retry budget;
* the archive-fallback flag is propagated to the persisted row.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Self

import pytest

from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services.download import attempt
from galleryvault.services.downloader import DownloadCancelledError, DownloadTask
from galleryvault.services.eh_client import (
    EhChallengeError,
    GalleryGoneError,
    GalleryReplacedError,
)


class _Row:
    def __init__(self, **kwargs: object) -> None:
        self.id = 1
        self.gid = 999
        self.token = "tok"
        self.title = "Test"
        self.status = "downloading"
        self.retry_count = 0
        self.max_retries = 5
        self.retry_at = None
        self.error_message = None
        self.updated_at = None
        self.finished_at = None
        for key, value in kwargs.items():
            setattr(self, key, value)


class _Session:
    def __init__(self, row: _Row | None) -> None:
        self.row = row

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> _Session:
        return self

    async def get(self, _model: object, _task_id: int) -> _Row | None:
        return self.row


class _TaskManager:
    def __init__(self) -> None:
        self._cancelled: set[int] = set()

    def is_cancelled(self, key: object) -> bool:
        return key in self._cancelled

    def request_cancel(self, key: object) -> None:
        self._cancelled.add(key)  # type: ignore[arg-type]

    def clear_cancelled(self, key: object) -> None:
        self._cancelled.discard(key)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _reset_state():
    attempt._challenge_counts.clear()
    original = {
        "settings": app_state.settings,
        "downloader": app_state.downloader,
        "session_factory": app_state.session_factory,
        "worker_session_factory": app_state.worker_session_factory,
        "task_manager": app_state.task_manager,
        "extra": dict(app_state.extra),
    }
    yield
    attempt._challenge_counts.clear()
    app_state.settings = original["settings"]
    app_state.downloader = original["downloader"]
    app_state.session_factory = original["session_factory"]
    app_state.worker_session_factory = original["worker_session_factory"]
    app_state.task_manager = original["task_manager"]
    app_state.extra.clear()
    app_state.extra.update(original["extra"])


def _patch_repository(monkeypatch: pytest.MonkeyPatch, recorded: list[tuple]) -> None:
    class FakeRepo:
        def __init__(self, _session: object) -> None:
            pass

        async def record_attempt(
            self, task_id: int, attempt_no: int, status: str, error: str | None = None
        ) -> None:
            recorded.append((task_id, attempt_no, status, error))

    monkeypatch.setattr(attempt, "DownloadRepository", FakeRepo)


def test_classify_error_matches_handler_order() -> None:
    assert attempt._classify_error(GalleryReplacedError(1, 2, "tok"))["kind"] == "replaced"
    assert attempt._classify_error(DownloadCancelledError("x"))["kind"] == "cancelled"
    assert attempt._classify_error(EhChallengeError("x"))["kind"] == "challenge"
    assert attempt._classify_error(GalleryGoneError("gone"))["kind"] == "error"

    gone = attempt._classify_error(GalleryGoneError("gone"))
    assert gone["gone"] is True
    assert gone["not_retryable"] is True
    assert "404" in gone["message"]

    text_gone = attempt._classify_error(RuntimeError("does not exist on ExHentai"))
    assert text_gone["gone"] is True
    assert text_gone["message"] == gone["message"]


def test_archive_fallback_flag_propagates() -> None:
    task = DownloadTask(999, "tok", "Test", id=1, archive_fallback=True)
    update_values: dict[str, object] = {}

    assert attempt._handle_archive_fallback(update_values, task) is True
    assert update_values["archive_fallback"] is True

    row = _Row()
    assert attempt._handle_archive_fallback(row, task) is True
    assert row.archive_fallback is True

    plain = DownloadTask(999, "tok", "Test", id=2)
    assert attempt._handle_archive_fallback({}, plain) is False


@pytest.mark.asyncio
async def test_over_budget_does_not_arm_pause_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Over budget fails the task instead of parking it in the pause/retry state.

    ``pause`` here is the per-task pending/retry state; the global 302 pause is
    still triggered afterwards, matching the D6 branch order.
    """
    row = _Row(retry_count=2, max_retries=5)
    monkeypatch.setattr(attempt, "_MAX_CHALLENGE_PAUSES", 1)
    monkeypatch.setattr(attempt, "_trigger_challenge_pause", _async_noop)
    recorded: list[tuple] = []
    _patch_repository(monkeypatch, recorded)

    task = DownloadTask(999, "tok", "Test", id=1, max_retries=5)
    await attempt._apply_retry_policy(lambda: _Session(row), task, EhChallengeError("302"))

    assert row.status == "failed"
    assert row.retry_at is None
    assert row.finished_at is not None
    assert "上限" in row.error_message
    assert row.retry_count < row.max_retries, "manual retry budget must survive"
    assert attempt.challenge_count(1) == 1
    assert recorded == [(1, 2, "challenged", "EhChallengeError")]


@pytest.mark.asyncio
async def test_cancelled_attempt_keeps_retry_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    app_state.settings = Settings(download_root=str(tmp_path), global_paused=False)
    app_state.task_manager = _TaskManager()
    row = _Row(retry_count=3, max_retries=5)
    app_state.session_factory = lambda: _Session(row)
    app_state.worker_session_factory = None

    async def _execute(*_args: object, **_kwargs: object) -> None:
        raise DownloadCancelledError("cancelled")

    app_state.downloader = SimpleNamespace(execute=_execute)
    recorded: list[tuple] = []
    _patch_repository(monkeypatch, recorded)

    await attempt._run_download_inner(DownloadTask(999, "tok", "Test", id=1, max_retries=5))

    assert row is not None
    assert row.status == "cancelled"
    assert row.retry_count == 3, "cancel must not consume the retry budget"
    assert recorded == [], "cancel must not record a failed attempt"


@pytest.mark.asyncio
async def test_archive_fallback_survives_failed_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _Row(retry_count=0, max_retries=5)
    recorded: list[tuple] = []
    _patch_repository(monkeypatch, recorded)

    task = DownloadTask(999, "tok", "Test", id=1, max_retries=5)
    exec_task = DownloadTask(999, "tok", "Test", id=1, max_retries=5, archive_fallback=True)
    await attempt._apply_retry_policy(
        lambda: _Session(row),
        task,
        RuntimeError("boom"),
        exec_task=exec_task,
    )

    assert row.archive_fallback is True
    assert row.status == "pending"
    assert row.retry_count == 1
    assert recorded and recorded[-1][2] == "failed"


async def _async_noop(*_args: object, **_kwargs: object) -> None:
    return None
