"""Cancellation must stop one run, not kill the resident worker loops.

INV-TASK-1: cancelling thumbs / tag-sync marks the run's terminal state and the
worker keeps polling, so a later ``generate`` / ``start`` works again.  Only
``asyncio.CancelledError`` (shutdown) may end the loop.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from galleryvault.app.exceptions import ConflictError
from galleryvault.app.routers import tasks as tasks_router
from galleryvault.app.state import app_state
from galleryvault.services import tag_sync_worker, thumbnail_worker
from galleryvault.services.tasks import TaskManager


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def begin(self):
        return self


class _FakeJobsRepo:
    def __init__(self, session):
        self.session = session

    async def mark_stale(self):
        return None


async def _wait_until(predicate, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("condition not met before timeout")
        await asyncio.sleep(0.01)


def _patch_common(monkeypatch, module, queue: list[tuple[int, int]], consumed: list[int], count):
    async def fake_claim(job_type, limit=1, **kwargs):
        return [queue.pop(0)] if queue else []

    async def fake_complete(job_type, gallery_id):
        return None

    async def fake_requeue(job_type, gallery_id, **kwargs):
        return None

    async def fake_jobs_count(job_type):
        return count()

    async def fake_gallery(gallery_id):
        consumed.append(gallery_id)
        return 1, 0

    monkeypatch.setattr(module, "claim_jobs", fake_claim)
    monkeypatch.setattr(module, "complete_job", fake_complete)
    monkeypatch.setattr(module, "requeue_job", fake_requeue)
    monkeypatch.setattr(module, "jobs_count", fake_jobs_count)
    monkeypatch.setattr(module, "BackgroundJobsRepository", _FakeJobsRepo)
    monkeypatch.setattr(module, "_get_background_session_factory", lambda: _FakeSession)
    return fake_gallery


def _cancelled_records(tm: TaskManager, task: str) -> list[dict]:
    return [
        record
        for record in tm.task_history
        if record.get("task") == task and record.get("status") == "cancelled"
    ]


@pytest.mark.asyncio
async def test_thumb_worker_survives_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    tm = TaskManager()
    tm.thumb_state["started_at"] = "2026-11-14T00:00:00+00:00"
    app_state.task_manager = tm
    app_state.settings = SimpleNamespace(thumbnail_workers=1)

    queue: list[tuple[int, int]] = []
    consumed: list[int] = []
    gallery = _patch_common(
        monkeypatch, thumbnail_worker, queue, consumed, lambda: len(queue)
    )
    monkeypatch.setattr(thumbnail_worker, "thumbnail_gallery", gallery)

    tm.request_cancel("thumbs")
    loop_task = asyncio.create_task(thumbnail_worker.thumbnail_worker_loop())

    await _wait_until(
        lambda: tm.thumb_state.get("running") is False
        and bool(tm.thumb_state.get("completed_at"))
    )

    assert _cancelled_records(tm, "thumbs"), "cancel must be recorded in task history"
    assert not loop_task.done(), "cancel must not terminate the resident worker loop"
    assert tm.is_cancelled("thumbs") is False, "cancel marker must be consumed"

    queue.append((42, 0))
    await _wait_until(lambda: consumed == [42])
    assert not loop_task.done(), "worker must keep consuming jobs after a cancel"

    loop_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(loop_task, timeout=1.0)


@pytest.mark.asyncio
async def test_tag_sync_worker_survives_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    tm = TaskManager()
    tm.tag_sync_state["started_at"] = "2026-11-14T00:00:00+00:00"
    app_state.task_manager = tm

    queue: list[tuple[int, int]] = []
    consumed: list[int] = []

    async def fake_sync_one(gallery_id, attempts):
        consumed.append(gallery_id)

    _patch_common(monkeypatch, tag_sync_worker, queue, consumed, lambda: len(queue))
    monkeypatch.setattr(tag_sync_worker, "_sync_one", fake_sync_one)
    monkeypatch.setattr(tag_sync_worker, "_worker_tasks", [])
    monkeypatch.setattr(tag_sync_worker, "_target_tag_sync_concurrency", 4)
    monkeypatch.setattr(tag_sync_worker, "_sync_event", None)
    monkeypatch.setattr(
        tag_sync_worker, "_sync_context", {"interval": 0.01, "last_activity": 0.0}
    )

    tm.request_cancel("tag-sync")

    async def runner() -> None:
        tag_sync_worker._worker_tasks = [asyncio.current_task()]
        await tag_sync_worker._tag_sync_worker()

    worker = asyncio.create_task(runner())
    await _wait_until(
        lambda: tm.tag_sync_state.get("running") is False
        and bool(tm.tag_sync_state.get("completed_at"))
    )

    assert _cancelled_records(tm, "tag-sync")
    assert not worker.done(), "cancel must not terminate the tag-sync worker"
    assert tm.is_cancelled("tag-sync") is False

    queue.append((77, 0))
    await _wait_until(lambda: consumed == [77])
    assert not worker.done()

    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(worker, timeout=1.0)


@pytest.mark.asyncio
async def test_cancel_idle_thumb_task_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    tm = TaskManager()
    app_state.task_manager = tm

    with pytest.raises(ConflictError) as exc_info:
        await tasks_router.cancel_background_task("thumbs")

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "no active thumbs task"
    assert tm.is_cancelled("thumbs") is False


@pytest.mark.asyncio
async def test_cancel_active_thumb_task_returns_202(monkeypatch: pytest.MonkeyPatch) -> None:
    tm = TaskManager()
    tm.thumb_state["running"] = True
    app_state.task_manager = tm
    cleared: list[str] = []

    async def fake_clear_jobs(job_type):
        cleared.append(job_type)

    monkeypatch.setattr(tasks_router, "_clear_jobs", fake_clear_jobs)

    result = await tasks_router.cancel_background_task("thumbs")

    assert result == {"task": "thumbs", "status": "cancelling"}
    assert tm.is_cancelled("thumbs") is True
    assert cleared == ["thumbs"]


@pytest.mark.asyncio
async def test_entrypoints_clear_stale_cancel_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    tm = TaskManager()
    app_state.task_manager = tm
    app_state.settings = SimpleNamespace(global_paused=False)

    spawned: list[str] = []

    def fake_spawn(coro, operation):
        spawned.append(operation)
        coro.close()
        return object()

    monkeypatch.setattr(tasks_router, "spawn_task", fake_spawn)
    monkeypatch.setattr(tasks_router, "_tag_sync_seed_state", {"running": False})

    tm.request_cancel("thumbs")
    thumbs = await tasks_router.trigger_thumbnail_generation()
    assert thumbs["status"] == "started"
    assert tm.is_cancelled("thumbs") is False
    tm.thumb_state["seeding"] = False

    tm.request_cancel("tag-sync")
    tag_sync = await tasks_router.trigger_tag_sync()
    assert tag_sync["status"] == "started"
    assert tm.is_cancelled("tag-sync") is False
    assert spawned == ["thumbnail seeding", "tag sync seeding"]
