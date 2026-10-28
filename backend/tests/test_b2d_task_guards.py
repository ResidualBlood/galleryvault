"""B2-D #17/#23: batch endpoints reject a second run and heavy seeding no
longer blocks the HTTP request."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from galleryvault.app.routers import favorites, series, tags, tasks, updates
from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services.tasks import TaskManager


@pytest.fixture
def task_manager(monkeypatch: pytest.MonkeyPatch) -> TaskManager:
    tm = TaskManager()
    monkeypatch.setattr(app_state, "task_manager", tm)
    return tm


def _consume_spawn(coro: object, operation: str) -> object:
    """Stand-in for spawn_task that closes the coroutine to avoid warnings."""
    close = getattr(coro, "close", None)
    if callable(close):
        close()
    return object()


async def test_compute_sizes_returns_409_when_metadata_sync_running(
    task_manager: TaskManager,
) -> None:
    task_manager.metadata_sync_state["running"] = True
    with pytest.raises(HTTPException) as exc:
        await favorites.compute_favorite_sizes(session=MagicMock())
    assert exc.value.status_code == 409


async def test_check_all_returns_409_when_check_running(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_state, "favorites_service", MagicMock())
    task_manager.favorites_check_state["running"] = True
    with pytest.raises(HTTPException) as exc:
        await favorites.check_all_favorites(session=MagicMock())
    assert exc.value.status_code == 409


async def test_updates_scan_returns_409_when_detecting(
    task_manager: TaskManager,
) -> None:
    task_manager.gallery_updates_state["detecting"] = True
    with pytest.raises(HTTPException) as exc:
        await updates.gallery_updates_scan()
    assert exc.value.status_code == 409


async def test_tag_translation_reload_returns_409_when_running(
    task_manager: TaskManager,
) -> None:
    task_manager.translation_state["running"] = True
    with pytest.raises(HTTPException) as exc:
        await tags.tag_translation_reload()
    assert exc.value.status_code == 409


async def test_tag_sync_start_rejects_when_global_paused(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_state, "settings", Settings(global_paused=True))
    result = await tasks.trigger_tag_sync()
    assert result["status"] == "paused"


async def test_tag_sync_start_returns_409_while_seeding(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_state, "settings", Settings(global_paused=False))
    monkeypatch.setitem(tasks._tag_sync_seed_state, "running", True)
    try:
        with pytest.raises(HTTPException) as exc:
            await tasks.trigger_tag_sync()
        assert exc.value.status_code == 409
    finally:
        tasks._tag_sync_seed_state["running"] = False


async def test_tag_sync_start_spawns_seeding_in_background(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_state, "settings", Settings(global_paused=False))
    calls: list[str] = []

    def _spawn(coro: object, operation: str) -> object:
        calls.append(operation)
        return _consume_spawn(coro, operation)

    monkeypatch.setattr(tasks, "spawn_task", _spawn)
    tasks._tag_sync_seed_state["running"] = False
    try:
        result = await tasks.trigger_tag_sync()
        assert result == {"status": "started", "queued": 0}
        assert calls == ["tag sync seeding"]
        assert tasks._tag_sync_seed_state["running"] is True
    finally:
        tasks._tag_sync_seed_state["running"] = False


async def test_tag_sync_seeding_pages_through_pending_ids(
    task_manager: TaskManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _SessionCtx:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *exc: object) -> bool:
            return False

    pages = {0: [11, 12], 12: [13], 13: []}

    class _Repo:
        def __init__(self, _session: object) -> None:
            pass

        async def pending_tag_sync_ids(self, limit: int, last_id: int) -> list[int]:
            return pages[last_id]

    enqueued: list[list[int]] = []

    async def _enqueue(ids: list[int]) -> None:
        enqueued.append(list(ids))

    monkeypatch.setattr(app_state, "session_factory", lambda: _SessionCtx())
    monkeypatch.setattr(tasks, "GalleryRepository", _Repo)
    monkeypatch.setattr(tasks, "enqueue_tag_sync", _enqueue)
    monkeypatch.setattr(tasks, "spawn_task", _consume_spawn)
    tasks._tag_sync_seed_state["running"] = True

    await tasks._seed_pending_tag_sync()

    assert enqueued == [[11, 12], [13]]
    assert tasks._tag_sync_seed_state["running"] is False
    assert task_manager.task_history[0]["reason"] == "queued 3 pending galleries"


async def test_series_rebuild_returns_409_while_running(
    task_manager: TaskManager,
) -> None:
    monkeypatch_running = series._series_rebuild_state
    monkeypatch_running["running"] = True
    try:
        with pytest.raises(HTTPException) as exc:
            await series.rebuild_series(dispatcher=None)
        assert exc.value.status_code == 409
    finally:
        monkeypatch_running["running"] = False
