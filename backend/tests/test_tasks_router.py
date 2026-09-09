import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from galleryvault.app.routers import tasks as tasks_router
from galleryvault.services.tasks import TaskManager


@pytest.fixture
def task_manager():
    tm = TaskManager()
    tm.thumb_state["seeding"] = False
    tm.thumb_state["running"] = False
    return tm


@pytest.fixture
def client(task_manager, monkeypatch):
    monkeypatch.setattr(tasks_router, "get_task_manager", lambda: task_manager)
    app = FastAPI()
    app.include_router(tasks_router.router)
    return TestClient(app)


def test_trigger_thumbnail_generation_success(client, task_manager, monkeypatch):
    captured_tasks = []

    def fake_spawn_task(coro, name=None):
        captured_tasks.append((coro, name))
        # Don't schedule automatically to verify initial return state first

    monkeypatch.setattr(tasks_router, "spawn_task", fake_spawn_task)

    resp = client.post("/api/thumbs/generate")
    assert resp.status_code == 202
    assert resp.json() == {"status": "started"}
    assert task_manager.thumb_state.get("seeding") is True
    assert len(captured_tasks) == 1
    assert captured_tasks[0][1] == "thumbnail seeding"

    # Now run the background closure to verify finally block and state transitions
    coro = captured_tasks[0][0]
    mock_seed = AsyncMock()
    mock_jobs_count = AsyncMock(return_value=5)
    monkeypatch.setattr(tasks_router, "seed_thumbnails", mock_seed)
    monkeypatch.setattr(tasks_router, "jobs_count", mock_jobs_count)

    asyncio.run(coro)

    assert mock_seed.await_count == 1
    assert mock_jobs_count.await_count == 1
    assert task_manager.thumb_state.get("running") is True
    assert task_manager.thumb_state.get("seeding") is False


def test_trigger_thumbnail_generation_reentrancy_protection(client, task_manager, monkeypatch):
    task_manager.thumb_state["seeding"] = True
    fake_spawn = MagicMock()
    monkeypatch.setattr(tasks_router, "spawn_task", fake_spawn)

    resp = client.post("/api/thumbs/generate")
    assert resp.status_code == 202
    assert resp.json() == {
        "status": "running",
        "message": "Thumbnail seeding already in progress",
    }
    fake_spawn.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_thumbnail_generation_closure_handles_error(task_manager, monkeypatch):
    captured_tasks = []

    def fake_spawn_task(coro, name=None):
        captured_tasks.append((coro, name))

    monkeypatch.setattr(tasks_router, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(tasks_router, "spawn_task", fake_spawn_task)

    mock_seed = AsyncMock(side_effect=RuntimeError("db connection failed"))
    monkeypatch.setattr(tasks_router, "seed_thumbnails", mock_seed)

    resp = await tasks_router.trigger_thumbnail_generation()
    assert resp == {"status": "started"}
    assert task_manager.thumb_state.get("seeding") is True
    assert len(captured_tasks) == 1

    # Run the closure and verify seeding flag is always cleaned up in finally
    with pytest.raises(RuntimeError, match="db connection failed"):
        await captured_tasks[0][0]

    assert task_manager.thumb_state.get("seeding") is False
