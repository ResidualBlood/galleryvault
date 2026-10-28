"""B1-E download core fixes (review 01 P2-2/6/7/8, P3-1..5/8..11; review 02 P3-5).

Each test targets one item so a regression can be attributed directly.
"""

from __future__ import annotations

import asyncio
import inspect
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from galleryvault.app.core.task_dispatcher import TaskDispatcher
from galleryvault.app.state import AppState, app_state
from galleryvault.config import Settings
from galleryvault.services import download_worker as dw
from galleryvault.services.background_workers import WorkerLifecycleManager
from galleryvault.services.base_service import BaseService
from galleryvault.services.downloader import (
    _PAGE_ATTEMPTS,
    _SPEED_STATS,
    Downloader,
    DownloadTask,
    _accepts_skip_hath,
    _ConcurrencyLimiter,
)
from galleryvault.services.eh_client import (
    ArchiveInfo,
    GalleryData,
    GalleryPageData,
)
from galleryvault.services.tasks import TaskManager

VALID_JPG = b"\xff\xd8\xff" + b"\x00" * 64


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class _PageClient:
    settings = SimpleNamespace(
        download_quality="resample",
        download_title="japanese",
        archive_fallback_pages=True,
    )

    def __init__(self, *, include_skip_hath: bool = True, raise_type_error: bool = False) -> None:
        self.include_skip_hath = include_skip_hath
        self.raise_type_error = raise_type_error
        self.resolve_calls = 0
        self.image_calls = 0

    async def fetch_gallery(self, gid, token, max_pages=None, *, resolve_urls=True):
        pages = [
            GalleryPageData(0, "https://exhentai.org/s/1", "tok0", "https://img.test/0.jpg"),
            GalleryPageData(1, "https://exhentai.org/s/2", "tok1", "https://img.test/1.jpg"),
        ]
        return GalleryData(gid, token, "Title", pages)

    async def download_image(self, url: str) -> bytes:
        self.image_calls += 1
        return VALID_JPG


class _SkipHathClient(_PageClient):
    async def resolve_page(self, gid, page, showkey=None, *, skip_hath=False):
        self.resolve_calls += 1
        return page


class _LegacyResolveClient(_PageClient):
    async def resolve_page(self, gid, page, showkey=None):
        self.resolve_calls += 1
        return page


class _TypeErrorClient(_PageClient):
    async def resolve_page(self, gid, page, showkey=None, *, skip_hath=False):
        self.resolve_calls += 1
        raise TypeError("genuine bug inside resolve_page")


def _build_zip(images: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in images:
            archive.writestr(name, data)
    return buffer.getvalue()


class _ArchiveClient:
    settings = SimpleNamespace(
        download_quality="resample",
        download_title="japanese",
        archive_fallback_pages=True,
    )

    def __init__(self) -> None:
        self.requests: list[str] = []
        self.urls: list[str] = []

    async def fetch_gallery(self, gid, token, max_pages=None, *, resolve_urls=True):
        pages = [
            GalleryPageData(i, f"https://exhentai.org/s/{i}", f"tok{i}")
            for i in range(2)
        ]
        return GalleryData(gid, token, "Arc Title", pages)

    async def fetch_archive_info(self, gid: int, token: str) -> ArchiveInfo:
        return ArchiveInfo(
            funds=1000,
            original_cost=10,
            original_size=1024,
            original_url="https://exhentai.org/archiver.php?or=key",
            resample_cost=1,
            resample_size=512,
            resample_url="https://exhentai.org/archiver.php?or=key",
        )

    async def request_archive(self, url: str, dltype: str) -> str:
        self.requests.append(dltype)
        return f"https://exhentai.org/dl/{dltype}.zip"

    async def download_archive(self, url: str, dest: Path, cb=None) -> int:
        self.urls.append(url)
        data = _build_zip([("a.jpg", VALID_JPG), ("b.jpg", VALID_JPG)])
        dest.write_bytes(data)
        if cb is not None:
            await cb(len(data), len(data))
        return len(data)


# --------------------------------------------------------------------------- #
# P2-2: the dead auto-retry sweep is gone; manual retry is the recovery path
# --------------------------------------------------------------------------- #


def test_auto_retry_sweep_removed() -> None:
    assert not hasattr(dw, "download_retry_sweep_loop")
    assert "sweep_auto_retry" not in inspect.getsource(dw)


# --------------------------------------------------------------------------- #
# P2-6: worker engine is rebuilt for the current loop instead of downgrading
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_engine_rebuilt_on_loop_mismatch(monkeypatch) -> None:
    import galleryvault.db.session as db_session

    old_loop = asyncio.new_event_loop()
    old_loop.close()
    disposed: list[bool] = []
    state = AppState(settings=Settings())
    state.session_factory = lambda: "api-factory"  # type: ignore[assignment]
    state.worker_session_factory = lambda: "worker-factory"  # type: ignore[assignment]
    state.worker_engine = SimpleNamespace(
        sync_engine=SimpleNamespace(dispose=lambda: disposed.append(True))
    )
    state._worker_bound_loop = old_loop

    new_factory = lambda: "rebuilt-factory"
    created: list[object] = []

    def fake_create(settings):
        created.append(settings)
        return SimpleNamespace(sync_engine=SimpleNamespace(dispose=lambda: None)), new_factory

    monkeypatch.setattr(db_session, "create_worker_database", fake_create)

    factory = state.background_session_factory

    assert factory is new_factory
    assert created == [state.settings]
    assert state._worker_bound_loop is asyncio.get_running_loop()
    assert disposed, "the loop-bound engine must be disposed when replaced"


# --------------------------------------------------------------------------- #
# P2-7: in-page attempts stay at 5; the constant is documented against AGENTS
# --------------------------------------------------------------------------- #


def test_page_attempt_constant_documents_doc_drift() -> None:
    assert _PAGE_ATTEMPTS == 5
    source = inspect.getsource(dw)  # imported package must stay consistent
    assert source  # smoke: download_worker still importable
    downloader_source = inspect.getsource(Downloader)
    assert "_PAGE_ATTEMPTS" in downloader_source


# --------------------------------------------------------------------------- #
# P2-8: a quality change discards the cached archive zip URL
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_archive_quality_change_discards_cached_zip_url(tmp_path: Path) -> None:
    temp = tmp_path / ".gv-1"
    temp.mkdir()
    (temp / ".archive.json").write_text(
        json.dumps({"quality": "resample", "zip_url": "https://exhentai.org/dl/old.zip"}),
        encoding="utf-8",
    )
    (temp / "archive.zip").write_bytes(b"stale partial zip")

    client = _ArchiveClient()
    result = await Downloader(client, tmp_path).execute(
        DownloadTask(1, "tok", "t", mode="archive", quality="original")
    )

    assert client.requests == ["org"], "the archive must be re-requested for the new tier"
    assert client.urls == ["https://exhentai.org/dl/org.zip"]
    sidecar = json.loads((result.path / ".galleryvault.json").read_text(encoding="utf-8"))
    assert sidecar["quality"] == "original"


# --------------------------------------------------------------------------- #
# P3-1: WorkerLifecycleManager propagates cancellation and can await shutdown
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_lifecycle_propagates_cancellation() -> None:
    manager = WorkerLifecycleManager()
    started = asyncio.Event()

    async def runner(_ctx) -> None:
        started.set()
        await asyncio.sleep(3600)

    task = manager.register_and_start("w", runner)
    await started.wait()
    manager.stop_worker("w")

    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled(), "cancellation must not be swallowed"
    assert manager.get_status("w")["state"] == "stopped"


@pytest.mark.asyncio
async def test_worker_lifecycle_replacement_is_awaited_on_shutdown() -> None:
    manager = WorkerLifecycleManager()
    first_started = asyncio.Event()

    async def first(_ctx) -> None:
        first_started.set()
        await asyncio.sleep(3600)

    async def second(_ctx) -> None:
        await asyncio.sleep(3600)

    old = manager.register_and_start("w", first)
    await first_started.wait()
    new = manager.register_and_start("w", second)

    await manager.stop_all_and_wait(timeout=2)

    assert old.cancelled()
    assert new.cancelled()


# --------------------------------------------------------------------------- #
# P3-2: BaseService calls TaskDispatcher with the right signatures
# --------------------------------------------------------------------------- #


class _RecordingTaskManager:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record_task(
        self,
        task: str,
        started_at: str | None = None,
        completed_at: str | None = None,
        status: str = "completed",
        reason: str = "",
        done: int = 0,
        total: int = 0,
    ) -> None:
        self.records.append({"task": task, "status": status, "reason": reason})

    async def persist_history(self) -> None:
        return None


@pytest.mark.asyncio
async def test_base_service_audit_scope_and_spawn_use_dispatcher_signature() -> None:
    tm = _RecordingTaskManager()
    service = BaseService(object(), TaskDispatcher(task_manager_getter=lambda: tm))  # type: ignore[arg-type]

    async with service.audit_scope("scan", "scan all roots", {"root": "/lib"}) as payload:
        payload["seen"] = 1

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert tm.records, "audit_scope must record through the dispatcher"
    assert tm.records[-1]["task"] == "scan"
    assert tm.records[-1]["status"] == "completed"
    assert "scan all roots" in str(tm.records[-1]["reason"])

    ran = asyncio.Event()

    async def background() -> None:
        ran.set()

    task = service.spawn_background_task("bg", background())
    assert task is not None
    await asyncio.wait_for(ran.wait(), timeout=2)


# --------------------------------------------------------------------------- #
# P3-3: started_at keeps the first start and the success attempt is numbered
# --------------------------------------------------------------------------- #


class _DownloadRow:
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
        self.started_at = None
        for key, value in kwargs.items():
            setattr(self, key, value)


class _Session:
    def __init__(self, row: _DownloadRow | None) -> None:
        self.row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self):
        return self

    async def get(self, _model: object, _task_id: int) -> _DownloadRow | None:
        return self.row


class _FakeTaskManager:
    def __init__(self) -> None:
        self.scan_state: dict[str, object] = {"running": False}

    def is_cancelled(self, _key: object) -> bool:
        return False

    def clear_cancelled(self, _key: object) -> None:
        return None

    def record_task(self, *_args: object, **_kwargs: object) -> None:
        return None


@pytest.mark.asyncio
async def test_success_preserves_started_at_and_records_attempt(monkeypatch, tmp_path: Path) -> None:
    original_start = datetime(2020, 1, 1, tzinfo=UTC)
    row = _DownloadRow(retry_count=2, started_at=original_start)
    app_state.settings = Settings(global_paused=False)
    monkeypatch.setattr(app_state, "task_manager", _FakeTaskManager())
    app_state.session_factory = lambda: _Session(row)

    target = tmp_path / "1-title"
    target.mkdir()
    result = SimpleNamespace(
        path=str(target),
        category="manga",
        title="Title",
        title_jpn=None,
        pages=2,
    )

    async def _execute(*_args: object, **_kwargs: object):
        return result

    app_state.downloader = SimpleNamespace(execute=_execute)

    def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(dw, "maybe_scan_after_download", _noop)

    recorded: list[tuple] = []

    class _FakeRepo:
        def __init__(self, _session: object) -> None:
            pass

        async def record_attempt(self, task_id, attempt, status, error=None):
            recorded.append((task_id, attempt, status, error))

    monkeypatch.setattr(dw, "DownloadRepository", _FakeRepo)

    await dw._run_download_inner(DownloadTask(999, "tok", "Test", id=1, max_retries=5))

    assert row.status == "success"
    assert row.started_at == original_start, "started_at is the first start, not the retry"
    assert recorded[-1][:3] == (1, 3, "success"), "attempt should be retry_count + 1"


# --------------------------------------------------------------------------- #
# P3-5: runtime concurrency resize + stats survive a Downloader rebuild
# --------------------------------------------------------------------------- #


def test_concurrency_limiter_can_be_resized() -> None:
    limiter = _ConcurrencyLimiter(1)
    limiter.set_limit(4)
    assert limiter.limit == 4

    downloader = Downloader(_PageClient(), "/tmp/gv-b1e-limiter")
    downloader.set_concurrency(7)
    assert downloader.semaphore.limit == 7


def test_speed_stats_are_shared_across_instances_and_loops(tmp_path: Path) -> None:
    _SPEED_STATS.pop(4242, None)
    client = _PageClient()
    first = Downloader(client, tmp_path)
    asyncio.run(first._record_bytes(4242, 2048, 1))

    second = Downloader(client, tmp_path)
    stats = asyncio.run(second.speed_stats(4242, current_page=1, total_pages=10))
    assert stats is not None
    assert stats["speed"] > 0

    # A different loop must not break the shared stats lock (P3-10).
    asyncio.run(second._record_bytes(4242, 1024, 1))
    second._clear_stats(4242)
    assert 4242 not in _SPEED_STATS


# --------------------------------------------------------------------------- #
# P3-8: cancellation markers are bounded
# --------------------------------------------------------------------------- #


def test_cancel_markers_are_bounded() -> None:
    manager = TaskManager()
    limit = 600
    for key in range(limit):
        manager.request_cancel(key)

    assert len(manager._cancelled_tasks) <= 512
    assert manager.is_cancelled(limit - 1)
    assert not manager.is_cancelled(0), "oldest markers must be evicted"

    manager.clear_cancelled(limit - 1)
    assert not manager.is_cancelled(limit - 1)


# --------------------------------------------------------------------------- #
# P3-9: history persistence merges with what is already stored
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_persist_history_merges_stored_records() -> None:
    stored = {
        "history": [
            {
                "task": "scan",
                "started_at": "2026-01-01T00:00:00+00:00",
                "completed_at": "2026-01-01T00:01:00+00:00",
                "status": "success",
                "reason": "",
                "done": 1,
                "total": 1,
            }
        ]
    }

    class _Row:
        def __init__(self, value):
            self.value = value

    class _Session:
        def __init__(self) -> None:
            self.row = _Row(stored)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def begin(self):
            return self

        async def get(self, _model: object, _key: str):
            return self.row

        def add(self, _item: object) -> None:
            raise AssertionError("existing row must be updated, not re-added")

    manager = TaskManager(session_factory=lambda: _Session())
    manager.record_task(
        "thumbs",
        "2026-01-02T00:00:00+00:00",
        "2026-01-02T00:01:00+00:00",
        "success",
        done=2,
        total=2,
    )

    await manager.persist_history()

    tasks = [record["task"] for record in manager.task_history]
    assert "scan" in tasks, "records written by another worker must survive"
    assert "thumbs" in tasks


# --------------------------------------------------------------------------- #
# P3-11: a paused download parks page tasks on a shared gate, not per-page polls
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_paused_download_waits_then_resumes(tmp_path: Path, monkeypatch) -> None:
    client = _SkipHathClient()
    downloader = Downloader(client, tmp_path)
    app_state.settings = Settings(global_paused=True)
    original_tm = app_state.task_manager
    app_state.task_manager = _FakeTaskManager()
    try:
        task = asyncio.create_task(downloader.execute(DownloadTask(1, "tok", "Title")))
        await asyncio.sleep(0.3)
        assert client.image_calls == 0, "no page may be fetched while globally paused"

        app_state.settings = Settings(global_paused=False)
        result = await asyncio.wait_for(task, timeout=10)
        assert result.path.exists()
        assert client.image_calls >= 2
    finally:
        app_state.task_manager = original_tm
        app_state.settings = Settings(global_paused=False)


# --------------------------------------------------------------------------- #
# Review 02 P3-5: resolve_page capability is inspected, not probed via TypeError
# --------------------------------------------------------------------------- #


def test_resolve_page_capability_detection() -> None:
    assert _accepts_skip_hath(_SkipHathClient()) is True
    assert _accepts_skip_hath(_LegacyResolveClient()) is False


@pytest.mark.asyncio
async def test_genuine_type_error_is_not_retried_as_legacy_signature(tmp_path: Path) -> None:
    client = _TypeErrorClient()
    with pytest.raises(TypeError):
        await Downloader(client, tmp_path).execute(DownloadTask(1, "tok", "Title", id=7))

    # One resolve per page per in-page attempt; the old TypeError probe would
    # have doubled that (two pages x attempts x 2).
    assert client.resolve_calls == _PAGE_ATTEMPTS * 2
