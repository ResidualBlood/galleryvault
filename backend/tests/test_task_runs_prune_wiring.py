"""T11.2c: startup restore wires the unbounded ``task_runs`` history to ``prune``.

The repository semantics themselves live in ``test_task_runs_repo.py``; here a
fake repository double pins the contract that ``TaskManager.restore_state``
prunes exactly once with the in-memory history limit and that a failing prune
never blocks startup.
"""

from __future__ import annotations

from typing import Any, ClassVar, Self

import pytest

from galleryvault.services import tasks as tasks_module
from galleryvault.services.tasks import TaskManager


class _FakeSession:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> _FakeSession:
        return self


class _FakeRunRepository:
    """Records prune calls; ``latest``/``mark_interrupted`` are restore no-ops."""

    keep_args: ClassVar[list[Any]] = []
    prune_error: ClassVar[Exception | None] = None

    def __init__(self, session: object) -> None:
        self.session = session

    @classmethod
    def reset(cls) -> None:
        cls.keep_args = []
        cls.prune_error = None

    async def mark_interrupted(self) -> int:
        return 0

    async def latest(self, name: str) -> Any | None:
        return None

    async def prune(self, keep_per_name: int = 20) -> int:
        type(self).keep_args.append(keep_per_name)
        if type(self).prune_error is not None:
            raise type(self).prune_error
        return 0


@pytest.fixture(autouse=True)
def _fake_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeRunRepository.reset()
    monkeypatch.setattr(tasks_module, "TaskRunRepository", _FakeRunRepository)


def _session_factory() -> _FakeSession:
    return _FakeSession()


@pytest.mark.asyncio
async def test_restore_state_prunes_once_with_history_limit() -> None:
    manager = TaskManager(session_factory=_session_factory)

    await manager.restore_state()

    assert _FakeRunRepository.keep_args == [200]
    assert _FakeRunRepository.keep_args == [tasks_module._HISTORY_LIMIT]


@pytest.mark.asyncio
async def test_prune_failure_only_warns(caplog: pytest.LogCaptureFixture) -> None:
    _FakeRunRepository.prune_error = RuntimeError("prune blew up")
    manager = TaskManager(session_factory=_session_factory)

    with caplog.at_level("WARNING", logger="galleryvault.services.tasks"):
        await manager.restore_state()

    assert _FakeRunRepository.keep_args == [200]
    assert any("failed to prune task run history" in record.message for record in caplog.records)
