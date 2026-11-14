"""T7.5: durable task state (task_runs) across restarts.

The ledger is exercised with an in-memory repository double so the tests stay
DB-free; the real repository semantics (partial unique index, CHECK) live in
``tests/test_task_runs_repo.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, ClassVar, Self

import pytest

from galleryvault.services import duplicate_groups as duplicate_groups_module
from galleryvault.services import tasks as tasks_module
from galleryvault.services.tasks import TaskManager


def _now() -> datetime:
    return datetime.now(UTC)


class _FakeSession:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> _FakeSession:
        return self


class _FakeRunRepository:
    """Minimal in-memory stand-in for TaskRunRepository."""

    rows: ClassVar[list[SimpleNamespace]] = []
    heartbeats: ClassVar[int] = 0

    def __init__(self, session: object) -> None:
        self.session = session

    @classmethod
    def reset(cls) -> None:
        cls.rows = []
        cls.heartbeats = 0

    async def start(
        self,
        name: str,
        *,
        run_id: str | None = None,
        stage: str | None = None,
        cancellable: bool = False,
        payload: Any = None,
        started_at: Any = None,
    ) -> str:
        for row in self.rows:
            if row.name == name and row.status == "running":
                row.status = "interrupted"
                row.completed_at = _now()
        rid = run_id or f"run-{len(self.rows) + 1}"
        row = SimpleNamespace(
            id=len(self.rows) + 1,
            name=name,
            run_id=rid,
            status="running",
            stage=stage,
            cancellable=cancellable,
            done=0,
            total=0,
            last_error=None,
            reason=None,
            started_at=started_at or _now(),
            completed_at=None,
            heartbeat_at=None,
            payload={},
        )
        self.rows.append(row)
        return rid

    async def heartbeat(
        self,
        name: str,
        done: int = 0,
        total: int = 0,
        stage: str | None = None,
        payload: Any = None,
        *,
        run_id: str | None = None,
    ) -> bool:
        type(self).heartbeats += 1
        for row in self.rows:
            if (
                row.name == name
                and row.status == "running"
                and (run_id is None or row.run_id == run_id)
            ):
                row.done = int(done)
                row.total = int(total)
                if stage is not None:
                    row.stage = stage
                row.heartbeat_at = _now()
                return True
        return False

    async def finish(
        self,
        name: str,
        status: str,
        reason: str = "",
        *,
        run_id: str | None = None,
        payload: Any = None,
        last_error: str | None = None,
        done: int | None = None,
        total: int | None = None,
        completed_at: Any = None,
    ) -> bool:
        for row in self.rows:
            if (
                row.name == name
                and row.status == "running"
                and (run_id is None or row.run_id == run_id)
            ):
                row.status = status
                row.reason = reason or None
                row.completed_at = completed_at or _now()
                if done is not None:
                    row.done = int(done)
                if total is not None:
                    row.total = int(total)
                if last_error is not None:
                    row.last_error = last_error
                return True
        return False

    async def record(
        self,
        name: str,
        status: str,
        *,
        run_id: str | None = None,
        started_at: Any = None,
        completed_at: Any = None,
        reason: str = "",
        done: int = 0,
        total: int = 0,
        last_error: str | None = None,
        payload: Any = None,
    ) -> str:
        rid = run_id or f"run-{len(self.rows) + 1}"
        self.rows.append(
            SimpleNamespace(
                id=len(self.rows) + 1,
                name=name,
                run_id=rid,
                status=status,
                stage=None,
                cancellable=False,
                done=int(done),
                total=int(total),
                last_error=last_error,
                reason=reason or None,
                started_at=started_at or _now(),
                completed_at=completed_at or _now(),
                heartbeat_at=None,
                payload={},
            )
        )
        return rid

    async def latest(self, name: str) -> SimpleNamespace | None:
        matching = [row for row in self.rows if row.name == name]
        return matching[-1] if matching else None

    async def history(self, limit: int = 50, *, name: str | None = None) -> list[Any]:
        rows = [row for row in self.rows if name is None or row.name == name]
        return list(reversed(rows))[:limit]

    async def mark_interrupted(self, reason: str = "interrupted by restart") -> int:
        count = 0
        for row in self.rows:
            if row.status == "running":
                row.status = "interrupted"
                row.reason = reason
                row.completed_at = _now()
                count += 1
        return count


@pytest.fixture(autouse=True)
def _fake_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeRunRepository.reset()
    monkeypatch.setattr(tasks_module, "TaskRunRepository", _FakeRunRepository)


def _session_factory() -> _FakeSession:
    return _FakeSession()


def _clock(monkeypatch: pytest.MonkeyPatch, start: float = 100.0) -> list[float]:
    now = [start]
    monkeypatch.setattr(tasks_module, "_monotonic", lambda: now[0])
    return now


@pytest.mark.asyncio
async def test_state_restored_after_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    now = _clock(monkeypatch)
    manager_a = TaskManager(session_factory=_session_factory)

    async with manager_a.track_task("scan", cancellable=True) as tracker:
        now[0] += 2.0
        tracker.update(scanned=5, total=10)
    await manager_a._drain_persist_jobs()

    assert manager_a.scan_state["scanned"] == 5
    completed_at = manager_a.scan_state["completed_at"]
    assert completed_at is not None

    manager_b = TaskManager(session_factory=_session_factory)
    await manager_b.restore_state()

    assert manager_b.scan_state["running"] is False
    assert manager_b.scan_state["completed_at"] == completed_at
    assert manager_b.scan_state["scanned"] == 5


@pytest.mark.asyncio
async def test_running_marked_interrupted_on_boot() -> None:
    manager_a = TaskManager(session_factory=_session_factory)
    await manager_a.begin_persisted_task("thumbs", cancellable=True)
    assert _FakeRunRepository.rows[-1].status == "running"

    manager_b = TaskManager(session_factory=_session_factory)
    await manager_b.restore_state()

    latest = _FakeRunRepository.rows[-1]
    assert latest.status == "interrupted"
    assert latest.reason == "interrupted by restart"
    assert latest.completed_at is not None
    assert manager_b.thumb_state["running"] is False
    assert manager_b.thumb_state["completed_at"] is not None


@pytest.mark.asyncio
async def test_tracker_update_is_throttled(monkeypatch: pytest.MonkeyPatch) -> None:
    now = _clock(monkeypatch)
    manager = TaskManager(session_factory=_session_factory)

    async with manager.track_task("scan") as tracker:
        tracker.update(scanned=1)
        tracker.update(scanned=2)
        await manager._drain_persist_jobs()
        assert _FakeRunRepository.heartbeats == 0

        now[0] += 1.5
        tracker.update(scanned=3)
        await manager._drain_persist_jobs()
        assert _FakeRunRepository.heartbeats == 1

        # A stage/status change bypasses the interval.
        tracker.update(stage="indexing")
        await manager._drain_persist_jobs()
        assert _FakeRunRepository.heartbeats == 2

        tracker.update(scanned=4)
        await manager._drain_persist_jobs()
        assert _FakeRunRepository.heartbeats == 2

    row = _FakeRunRepository.rows[-1]
    assert row.status == "success"
    assert row.done == 4


@pytest.mark.asyncio
async def test_database_unavailable_only_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken_factory() -> Any:
        raise RuntimeError("database down")

    manager = TaskManager(session_factory=broken_factory)
    with caplog.at_level("WARNING", logger="galleryvault.services.tasks"):
        async with manager.track_task("scan") as tracker:
            tracker.update(scanned=1)
    assert manager.scan_state["running"] is False
    assert manager.task_history[0]["status"] == "success"
    assert any("failed to open task run" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_record_task_persists_finished_run() -> None:
    manager = TaskManager(session_factory=_session_factory)
    now = _now().isoformat()
    manager.record_task("gallery-delete", now, now, "success", reason="deleted", done=2, total=2)
    await manager._drain_persist_jobs()

    row = _FakeRunRepository.rows[-1]
    assert row.name == "gallery-delete"
    assert row.status == "success"
    assert row.done == 2

    # TaskDispatcher reports "completed"; the ledger only stores canonical values.
    manager.record_task("list-add", now, now, "completed", reason="ok")
    await manager._drain_persist_jobs()
    assert _FakeRunRepository.rows[-1].status == "success"


@pytest.mark.asyncio
async def test_history_records_reads_task_runs() -> None:
    manager = TaskManager(session_factory=_session_factory)
    now = _now()
    _FakeRunRepository.rows.extend(
        [
            SimpleNamespace(
                id=1,
                name="scan",
                run_id="run-1",
                status="success",
                stage=None,
                cancellable=True,
                done=7,
                total=10,
                last_error=None,
                reason="",
                started_at=now,
                completed_at=now,
                heartbeat_at=now,
                payload={},
            ),
            SimpleNamespace(
                id=2,
                name="thumbs",
                run_id="run-2",
                status="running",
                stage="generating",
                cancellable=True,
                done=1,
                total=4,
                last_error=None,
                reason=None,
                started_at=now,
                completed_at=None,
                heartbeat_at=now,
                payload={},
            ),
        ]
    )

    finished = await manager.history_records()

    assert [record["task"] for record in finished] == ["scan"]
    assert finished[0] == {
        "task": "scan",
        "started_at": now.isoformat(),
        "completed_at": now.isoformat(),
        "status": "success",
        "reason": "",
        "done": 7,
        "total": 10,
    }


@pytest.mark.asyncio
async def test_duplicates_ready_reads_task_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace(status="success", completed_at=_now())

    class _OrSession:
        async def scalar(self, _stmt: object) -> None:
            return None

        async def get(self, _model: object, _key: str) -> None:
            raise AssertionError("ready must not read app_config for cross_gid")

    class _ReadyRepository:
        def __init__(self, session: object) -> None:
            self.session = session

        async def latest(self, name: str) -> SimpleNamespace | None:
            assert name == "duplicates-cross-gid"
            return state

    monkeypatch.setattr(duplicate_groups_module, "TaskRunRepository", _ReadyRepository)
    assert await duplicate_groups_module.kind_scanned(_OrSession(), "cross_gid") is True

    state.status = "running"
    state.completed_at = None
    assert await duplicate_groups_module.kind_scanned(_OrSession(), "cross_gid") is False

    class _EmptyRepository:
        def __init__(self, session: object) -> None:
            self.session = session

        async def latest(self, name: str) -> None:
            return None

    monkeypatch.setattr(duplicate_groups_module, "TaskRunRepository", _EmptyRepository)
    assert await duplicate_groups_module.kind_scanned(_OrSession(), "cross_gid") is False


def test_begin_task_keeps_legacy_state_shape() -> None:
    manager = TaskManager()
    manager.begin_task("scan", cancellable=True)
    assert manager.scan_state["running"] is True
    assert manager.scan_state["cancellable"] is True
    assert "scanned" not in manager.scan_state

    manager.mark_cancelling("scan")
    assert manager.scan_state["running"] is False
    assert manager.scan_state["status"] == "cancelling"
