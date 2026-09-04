"""Regression tests for the cancel/completion race in run_download.

A user can hit cancel just as a download finishes: the last progress callback
already ran (so no DownloadCancelledError was raised mid-flight), but the
cancel route has flipped the DB row to "cancelled" and armed the in-flight
flag.  The old success branch ignored both signals and either marked the task
success or left a "success" attempt + an "ok" notification behind.  The branch
now re-checks the row status and the flag inside its transaction and raises
DownloadCancelledError so the shared cancel-cleanup path (temp dir, flag, no
"ok" notification) runs.
"""

from pathlib import Path

import pytest

from galleryvault.app.state import app_state
from galleryvault.services import download_worker
from galleryvault.services.download_worker import run_download
from galleryvault.services.downloader import DownloadResult, DownloadTask


class _Row:
    def __init__(self, task_id: int):
        self.id = task_id
        self.gid = 7
        self.token = "token"
        self.status = "downloading"
        self.retry_count = 0
        self.max_retries = 10
        self.target_path = None
        self.category = None
        self.error_message = None
        self.retry_at = None
        self.finished_at = None
        self.started_at = None


class _Session:
    """Fake session whose row snapshot is chosen per read.

    ``row_provider`` returns the row the next ``get`` should hand back, so a
    test can flip the row to "cancelled" between the pre-flight read and the
    final-commit read, exactly like the cancel route does.
    """

    def __init__(self, row_provider):
        self._provider = row_provider
        self.attempts: list[tuple[int, int, str]] = []
        self.committed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def begin(self):
        return self

    async def get(self, model, pk):
        row = self._provider()
        row.id = pk
        return row

    def add(self, obj):
        self.attempts.append((obj.task_id, obj.attempt, obj.status))

    async def flush(self):
        pass


class _Downloader:
    root = None

    def __init__(self, result, cancel_between=False):
        self.result = result
        self.cancel_between = cancel_between
        self.cancelled_now = False

    async def execute(self, task, *, progress=None, **_):
        if self.cancel_between:
            self.cancelled_now = True
            app_state.task_manager.request_cancel(task.id)
        return self.result


class _Settings:
    def __init__(self, root: Path):
        self.download_root = str(root)
        self.telegram_notify_level = "always"


def _patched(monkeypatch, *, row_provider, downloader):
    """Stub the DB + downloader + notification seams run_download touches."""
    monkeypatch.setattr(app_state, "session_factory", lambda: _Session(row_provider))
    monkeypatch.setattr(app_state, "downloader", downloader)
    monkeypatch.setattr(app_state, "settings", _Settings(Path("/tmp")))
    monkeypatch.setattr(download_worker, "maybe_scan_after_download", lambda result: None)
    notifications: list[tuple[str, object, object]] = []

    async def record_notification(kind, title, detail=None):
        notifications.append((kind, title, detail))

    monkeypatch.setattr(download_worker, "record_download_notification", record_notification)
    return notifications


@pytest.mark.asyncio
async def test_cancel_lands_after_download_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cancel armed just before the final commit must not mark success.

    The last progress callback has already run, so execute() returns normally;
    but the cancel route has set the flag (and flipped the DB row) by the time
    the success branch commits.  The task must stay cancelled, no success
    attempt, no "ok" notification, and the flag must be consumed.
    """
    row = _Row(42)
    phase = [0]

    def row_provider():
        # First read: task is being claimed.  Second read: cancel committed.
        phase[0] += 1
        if phase[0] >= 2:
            row.status = "cancelled"
        return row

    result = DownloadResult(gid=7, path=Path("/tmp/dl"), pages=5, category="manga", title="t")
    notifications = _patched(
        monkeypatch,
        row_provider=row_provider,
        downloader=_Downloader(result, cancel_between=True),
    )

    await run_download(DownloadTask(7, "token", "t", id=42))

    assert row.status == "cancelled", "task must stay cancelled"
    assert not app_state.task_manager.is_cancelled(42), "in-flight flag must be discarded"
    assert notifications == [], "no ok notification for a cancelled download"


@pytest.mark.asyncio
async def test_cancel_via_db_status_before_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The row already reads "cancelled" when the success branch commits.

    The cancel route's DB commit happened before the success branch read the
    row (flag path above covers the in-between window).  Same expectations.
    """
    row = _Row(43)
    phase = [0]

    def row_provider():
        phase[0] += 1
        if phase[0] >= 2:
            row.status = "cancelled"
        return row

    result = DownloadResult(gid=7, path=Path("/tmp/dl"), pages=5, category="manga", title="t")
    notifications = _patched(
        monkeypatch,
        row_provider=row_provider,
        downloader=_Downloader(result),
    )

    await run_download(DownloadTask(7, "token", "t", id=43))

    assert row.status == "cancelled"
    assert not app_state.task_manager.is_cancelled(43)
    assert notifications == []


@pytest.mark.asyncio
async def test_success_path_when_no_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a cancel the success branch still marks success + notifies."""
    row = _Row(44)

    def row_provider():
        return row

    result = DownloadResult(gid=7, path=Path("/tmp/dl"), pages=5, category="manga", title="t")
    notifications = _patched(
        monkeypatch,
        row_provider=row_provider,
        downloader=_Downloader(result),
    )

    await run_download(DownloadTask(7, "token", "t", id=44))

    assert row.status == "success"
    assert row.target_path == "/tmp/dl"
    assert row.retry_count == 0
    assert notifications == [("ok", "t", "5")]


@pytest.mark.asyncio
async def test_gallery_gone_error_marks_failed_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """GalleryGoneError (404) must fail immediately and exhaust the retry budget."""
    from galleryvault.services.eh_client import GalleryGoneError

    class _FailingDownloader:
        root = None

        async def execute(self, task, *, progress=None, **_):
            raise GalleryGoneError("gallery does not exist on ExHentai (404)")

    row = _Row(45)

    def row_provider():
        return row

    notifications = _patched(
        monkeypatch,
        row_provider=row_provider,
        downloader=_FailingDownloader(),
    )

    await run_download(DownloadTask(7, "token", "t", id=45))

    assert row.status == "failed"
    assert row.retry_at is None
    assert row.retry_count >= row.max_retries
    assert "deleted or not found" in (row.error_message or "")
    assert len(notifications) == 1
    assert notifications[0][0] == "fail"


@pytest.mark.asyncio
async def test_cancel_pending_task_arms_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers import downloads as dl_router
    from galleryvault.app.routers.downloads import cancel_download

    row = _Row(99)
    row.status = "pending"

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def begin(self):
            return self

        async def get(self, model, pk):
            return row

    class FakeRepo:
        def __init__(self, session):
            pass

        async def cancel(self, task_id):
            row.status = "cancelled"
            return True

    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr(dl_router, "get_session", fake_get_session)
    monkeypatch.setattr(dl_router, "DownloadRepository", FakeRepo)

    res = await cancel_download(99)
    assert res == {"id": 99, "status": "cancelled"}
    assert app_state.task_manager.is_cancelled(99)
    app_state.task_manager.clear_cancelled(99)


@pytest.mark.asyncio
async def test_worker_pending_cancelled_task_skips_download(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _Row(101)
    row.status = "pending"
    app_state.task_manager.request_cancel(101)

    executed = []

    class _TrackingDownloader:
        root = None

        async def execute(self, *args, **kwargs):
            executed.append(True)
            raise AssertionError("execute should not be called")

    notifications = _patched(
        monkeypatch,
        row_provider=lambda: row,
        downloader=_TrackingDownloader(),
    )

    await run_download(DownloadTask(7, "token", "t", id=101))

    assert executed == []
    assert row.status == "cancelled"
    assert not app_state.task_manager.is_cancelled(101)
    assert notifications == []
