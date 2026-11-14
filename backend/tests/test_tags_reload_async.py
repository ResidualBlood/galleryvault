"""T1.5: tag-translation reload must hand off to a background task.

``POST /api/tags/search/reload`` used to await the whole EhTagTranslation
download (measured 6.7s) and still answer 202.  It now answers immediately and
the frontend polls ``GET /api/tags/search/status`` for completion.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi import HTTPException

from galleryvault.app.routers import tags
from galleryvault.app.state import app_state
from galleryvault.services.tasks import TaskManager


@pytest.fixture
def task_manager(monkeypatch: pytest.MonkeyPatch) -> TaskManager:
    tm = TaskManager()
    monkeypatch.setattr(app_state, "task_manager", tm)
    return tm


class _SpawnRecorder:
    """Record spawned coroutines as real tasks so the test can await them."""

    def __init__(self) -> None:
        self.operations: list[str] = []
        self.tasks: list[asyncio.Task[Any]] = []

    def __call__(self, coroutine: Any, operation: str) -> asyncio.Task[Any]:
        self.operations.append(operation)
        task = asyncio.ensure_future(coroutine)
        self.tasks.append(task)
        return task


def _install_slow_update(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[asyncio.Event, asyncio.Event]:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_update() -> bool:
        started.set()
        await release.wait()
        return True

    monkeypatch.setattr(tags, "translation_update_once", slow_update)
    return started, release


async def test_reload_returns_before_update_finishes(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, release = _install_slow_update(monkeypatch)
    recorder = _SpawnRecorder()
    monkeypatch.setattr(tags, "spawn_task", recorder, raising=False)

    began = time.monotonic()
    result = await asyncio.wait_for(tags.tag_translation_reload(), timeout=1.0)
    elapsed = time.monotonic() - began

    assert result == {"accepted": True}
    assert elapsed < 0.5
    assert recorder.operations == ["tag translation update"]
    # Claiming the run before the coroutine starts closes the double-submit race.
    assert task_manager.translation_state["running"] is True

    await asyncio.sleep(0)
    assert started.is_set()
    release.set()
    await recorder.tasks[0]


async def test_reload_409_when_running_and_does_not_spawn(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_manager.translation_state["running"] = True
    calls: list[tuple[object, str]] = []

    def _spawn(coroutine: object, operation: str) -> object:
        calls.append((coroutine, operation))
        return object()

    monkeypatch.setattr(tags, "spawn_task", _spawn, raising=False)
    with pytest.raises(HTTPException) as exc:
        await tags.tag_translation_reload()

    assert exc.value.status_code == 409
    assert calls == []


async def test_reload_returns_503_when_background_unavailable(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _update() -> bool:
        return True

    def _unavailable(coroutine: Any, _operation: str) -> None:
        coroutine.close()

    monkeypatch.setattr(tags, "translation_update_once", _update)
    monkeypatch.setattr(tags, "spawn_task", _unavailable, raising=False)

    with pytest.raises(HTTPException) as exc:
        await tags.tag_translation_reload()

    assert exc.value.status_code == 503
    assert task_manager.translation_state["running"] is False


async def test_status_exposes_running_and_last_error(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_manager.translation_state.update(running=True, last_error=None)
    monkeypatch.setattr(tags, "translation_entry_count", lambda: 45161)

    status = await tags.tag_translation_status()

    assert status["running"] is True
    assert status["last_error"] is None
    assert status["entries"] == 45161


async def test_reload_completion_clears_running(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real tracker lifecycle still flips the shared state back to idle."""

    async def update() -> bool:
        # Mirrors translation_update_once: owns the track_task lifecycle.
        async with task_manager.track_task("translation") as tracker:
            await asyncio.sleep(0)
            tracker.update(entries=42, last="2026-01-01T00:00:00+00:00", last_error=None)
        return True

    monkeypatch.setattr(tags, "translation_update_once", update)
    recorder = _SpawnRecorder()
    monkeypatch.setattr(tags, "spawn_task", recorder, raising=False)

    assert (await tags.tag_translation_reload()) == {"accepted": True}
    assert task_manager.translation_state["running"] is True

    await recorder.tasks[0]
    state = task_manager.translation_state
    assert state["running"] is False
    assert state["last_error"] is None
    assert state["entries"] == 42
