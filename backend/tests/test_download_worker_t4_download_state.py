"""Task T4: download state machine, cancellation and worker supervision.

Covers:
- a replaced gallery whose retarget fails must not stay ``downloading``;
- 302 challenges use their own budget and keep the retry budget intact;
- a download finishing during a full scan is deferred, not silently dropped;
- cancelling a page batch leaves no orphan writer touching ``.gv-<gid>``;
- the delete endpoint waits for an active worker before removing the temp dir;
- the supervisor restarts a crashed worker with backoff.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Self

import pytest
from PIL import Image as PILImage

from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services import download_worker as dw
from galleryvault.services.downloader import (
    DownloadCancelledError,
    Downloader,
    DownloadTask,
)
from galleryvault.services.eh_client import (
    EhChallengeError,
    GalleryData,
    GalleryPageData,
    GalleryReplacedError,
)

PNG_BYTES = io.BytesIO()


def _png() -> bytes:
    PILImage.new("RGB", (4, 4)).save(PNG_BYTES, format="PNG")
    return PNG_BYTES.getvalue()


class _FakeTaskManager:
    def __init__(self, *, scan_running: bool = False) -> None:
        self.scan_state: dict[str, object] = {"running": scan_running}
        self.records: list[dict[str, object]] = []
        self._cancelled: set[int] = set()

    def record_task(
        self,
        task: str,
        started_at: str | None,
        completed_at: str | None,
        status: str,
        reason: str = "",
        done: int = 0,
        total: int = 0,
    ) -> None:
        self.records.append(
            {
                "task": task,
                "status": status,
                "reason": reason,
                "done": done,
                "total": total,
            }
        )

    def is_cancelled(self, task_key: object) -> bool:
        return task_key in self._cancelled

    def request_cancel(self, task_key: object) -> None:
        self._cancelled.add(task_key)  # type: ignore[arg-type]

    def clear_cancelled(self, task_key: object) -> None:
        self._cancelled.discard(task_key)  # type: ignore[arg-type]


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


@pytest.fixture(autouse=True)
def _reset_worker_state():
    dw._pending_ingests.clear()
    dw._challenge_counts.clear()
    yield
    dw._pending_ingests.clear()
    dw._challenge_counts.clear()
    pump = dw._ingest_pump_task
    dw._ingest_pump_task = None
    if pump is not None and not pump.done():
        pump.cancel()


def _patch_repository(monkeypatch, recorded: list[tuple]) -> None:
    class FakeRepo:
        def __init__(self, _session: object) -> None:
            pass

        async def record_attempt(
            self, task_id: int, attempt: int, status: str, error: str | None = None
        ) -> None:
            recorded.append((task_id, attempt, status, error))

    monkeypatch.setattr(dw, "DownloadRepository", FakeRepo)


@pytest.mark.asyncio
async def test_replacement_skip_writes_terminal_state(monkeypatch) -> None:
    app_state.settings = Settings(global_paused=False)
    app_state.extra.clear()
    app_state.task_manager = _FakeTaskManager()
    row = _Row(retry_count=2)
    app_state.session_factory = lambda: _Session(row)

    mock_downloader = type("D", (), {})()
    raised = GalleryReplacedError(999, 1000, "newtok")

    async def _execute(*_args: object, **_kwargs: object) -> None:
        raise raised

    mock_downloader.execute = _execute
    app_state.downloader = mock_downloader

    async def _no_replacement(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(dw, "_apply_replacement", _no_replacement)
    recorded: list[tuple] = []
    _patch_repository(monkeypatch, recorded)

    await dw._run_download_inner(DownloadTask(999, "tok", "Test", id=1, max_retries=5))

    assert row.status == "failed", "replacement skip must not leave the task downloading"
    assert row.retry_at is None
    assert row.finished_at is not None
    assert row.retry_count == row.max_retries
    assert "替换链未能重定向" in row.error_message
    assert recorded and recorded[-1][2] == "failed"


@pytest.mark.asyncio
async def test_challenge_budget_is_separate_and_capped(monkeypatch) -> None:
    app_state.settings = Settings(global_paused=False)
    app_state.extra.clear()
    app_state.task_manager = _FakeTaskManager()
    row = _Row(retry_count=0, max_retries=5)
    app_state.session_factory = lambda: _Session(row)

    async def _execute(*_args: object, **_kwargs: object) -> None:
        raise EhChallengeError("ExHentai 302 challenge")

    app_state.downloader = type("D", (), {"execute": staticmethod(_execute)})()

    paused: list[object] = []

    async def _fake_pause(*args: object, **kwargs: object) -> None:
        paused.append((args, kwargs))

    monkeypatch.setattr(dw, "_trigger_challenge_pause", _fake_pause)
    monkeypatch.setattr(dw, "_MAX_CHALLENGE_PAUSES", 2)
    recorded: list[tuple] = []
    _patch_repository(monkeypatch, recorded)

    task = DownloadTask(999, "tok", "Test", id=1, max_retries=5)

    await dw._run_download_inner(task)
    assert row.status == "pending"
    assert row.retry_count == 0, "a challenge pause must not consume the retry budget"
    assert dw.challenge_count(1) == 1
    assert "1/2" in row.error_message

    await dw._run_download_inner(task)
    assert row.status == "failed", "challenge budget must terminate the pause/resume loop"
    assert row.retry_at is None
    assert row.retry_count < row.max_retries, "keep retry budget for rearm_failed"
    assert "上限" in row.error_message
    assert dw.challenge_count(1) == 2
    assert len(paused) == 2


@pytest.mark.asyncio
async def test_completed_download_during_scan_is_deferred(monkeypatch) -> None:
    tm = _FakeTaskManager(scan_running=True)
    app_state.task_manager = tm
    ingested: list[object] = []

    async def _fake_ingest(result: object) -> None:
        ingested.append(result)

    monkeypatch.setattr(dw, "ingest_downloaded_gallery", _fake_ingest)
    monkeypatch.setattr(dw, "_INGEST_PUMP_INTERVAL", 0.01)

    result = type("R", (), {"gid": 42, "path": "/tmp/gv-42"})()
    dw.maybe_scan_after_download(result)

    assert ingested == []
    assert dw.pending_ingest_count() == 1
    assert tm.records and tm.records[-1]["status"] == "pending"
    assert tm.records[-1]["task"] == "download-ingest"

    tm.scan_state["running"] = False
    for _ in range(200):
        if ingested:
            break
        await asyncio.sleep(0.01)

    assert ingested == [result], "the deferred ingest must run once the scan finishes"
    assert dw.pending_ingest_count() == 0
    assert tm.records[-1]["status"] == "success"


@pytest.mark.asyncio
async def test_cancel_cancels_sibling_page_writers(monkeypatch, tmp_path: Path) -> None:
    gallery_root = tmp_path
    gate = asyncio.Event()
    started = asyncio.Event()

    class FakeClient:
        async def fetch_gallery(
            self,
            gid: int,
            token: str,
            max_pages: int | None = None,
            *,
            resolve_urls: bool = True,
        ) -> GalleryData:
            return GalleryData(
                gid=gid,
                token=token,
                title="Test",
                pages=[GalleryPageData(i, f"https://example.test/u{i}", "t") for i in range(2)],
            )

        async def resolve_page(
            self,
            _gid: int,
            page: GalleryPageData,
            _showkey: object = None,
            *,
            skip_hath: bool = False,
        ) -> GalleryPageData:
            return page

        async def download_image(self, url: str) -> bytes:
            if url.endswith("u1"):
                raise DownloadCancelledError("cancelled on page 2")
            started.set()
            await gate.wait()
            return _png()

    app_state.settings = Settings(global_paused=False)
    app_state.task_manager = _FakeTaskManager()
    downloader = Downloader(FakeClient(), gallery_root, concurrency=1, page_concurrency=2)

    task = DownloadTask(4242, "tok", "Test", id=7)
    with pytest.raises(DownloadCancelledError):
        await asyncio.wait_for(downloader._download_pages(task), timeout=5)

    temp = gallery_root / ".gv-4242"
    written_before = sorted(p.name for p in temp.iterdir()) if temp.exists() else []

    gate.set()
    await asyncio.sleep(0.05)

    written_after = sorted(p.name for p in temp.iterdir()) if temp.exists() else []
    assert written_after == written_before, "no orphan page task may write after cancellation"
    assert not any(name.endswith(".png") for name in written_after)


@pytest.mark.asyncio
async def test_delete_cleanup_waits_for_active_worker(tmp_path: Path) -> None:
    from galleryvault.app.routers import downloads as downloads_router

    root = tmp_path
    temp = root / ".gv-77"
    temp.mkdir()
    (temp / "00000001.png").write_bytes(b"partial")
    app_state.settings = Settings(download_root=str(root))

    class ActiveDownloader:
        async def wait_idle(self, _gid: int, timeout: float = 0.0) -> bool:
            return False

    app_state.downloader = ActiveDownloader()
    await downloads_router._cleanup_download_temp(77)
    assert temp.exists(), "an active worker must block temp deletion"

    class IdleDownloader:
        async def wait_idle(self, _gid: int, timeout: float = 0.0) -> bool:
            return True

    app_state.downloader = IdleDownloader()
    await downloads_router._cleanup_download_temp(77)
    assert not temp.exists()


@pytest.mark.asyncio
async def test_supervise_worker_restarts_after_crash() -> None:
    from galleryvault.app.lifespan import supervise_worker

    calls: list[int] = []

    async def factory() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")

    await asyncio.wait_for(
        supervise_worker("crasher", factory, initial_delay=0, max_delay=0), timeout=5
    )
    assert len(calls) == 2, "a crashed worker must be restarted"

    async def cancelled() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await supervise_worker("cancelled", cancelled, initial_delay=0, max_delay=0)
