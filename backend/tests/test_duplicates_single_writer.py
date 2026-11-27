"""T5.2: every duplicate scanner writes ``duplicate_groups`` and nothing else.

RED targets from PLAN-backend-hardening Batch 5:

* the cross-gid scan persists its groups through
  ``DuplicateGroupRepository.sync('cross_gid', ...)`` (T5.3 removed the
  process-local ``app_state.cross_gid_duplicates`` snapshot entirely);
* the favorites duplicate scan persists through
  ``DuplicateGroupRepository.sync('favorites', ...)`` while
  ``tm.duplicates_state`` keeps progress only;
* ``POST /api/library/duplicates/cross-gid/refresh`` answers 202 without
  waiting for the scan and returns 409 while one is already running.
"""

from __future__ import annotations

import asyncio
import time
from typing import ClassVar

import pytest
from fastapi import HTTPException

from galleryvault.app import state as state_module
from galleryvault.app.routers import duplicates as duplicates_router
from galleryvault.services import duplicates as duplicates_service
from galleryvault.services.duplicates import (
    cross_gid_scan_lock,
    scan_library_cross_gid_groups,
)
from galleryvault.services.maintain import favorite_duplicates
from galleryvault.services.tasks import TaskManager


class _Rows(list):
    def all(self):
        return list(self)


class _FakeSession:
    last_marker = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def scalars(self, stmt):
        return _Rows([])

    async def get(self, model, pk):
        return None

    def add(self, row):
        _FakeSession.last_marker = getattr(row, "key", None)

    async def flush(self):
        return None


def _session_factory():
    class _Factory:
        def __call__(self):
            class _Ctx:
                async def __aenter__(self):
                    return _FakeSession()

                async def __aexit__(self, *args):
                    return False

            return _Ctx()

    return _Factory()


class _FakeFavoritesRepo:
    def __init__(self, session):
        pass

    async def artist_tags_for_gallery_ids(self, gallery_ids):
        return {}

    async def tags_for_gallery_ids(self, gallery_ids):
        return {}

    async def ignored_duplicate_keys(self):
        return set()

    async def ignored_duplicates(self):
        return []


class _RecordingDuplicateRepo:
    """Stands in for ``DuplicateGroupRepository``; records ``sync`` calls."""

    calls: ClassVar[list[tuple[str, list]]] = []

    def __init__(self, session):
        self.session = session

    async def sync(self, kind, groups):
        _RecordingDuplicateRepo.calls.append((kind, list(groups)))
        return []


@pytest.fixture(autouse=True)
def _reset_recorder():
    _RecordingDuplicateRepo.calls = []
    yield
    _RecordingDuplicateRepo.calls = []


def _cross_gid_group() -> dict:
    return {
        "key": "alice|book",
        "artist": "alice",
        "legacy_keys": ["alice|book_old"],
        "items": [
            {"gallery_id": 10, "gid": 1001, "title": "[Alice] Book"},
            {"gallery_id": None, "gid": 1002, "title": "[Alice] Book [DL版]"},
        ],
    }


@pytest.mark.asyncio
async def test_cross_gid_scan_persists_groups(monkeypatch):
    monkeypatch.setattr("galleryvault.db.repository.FavoritesRepository", _FakeFavoritesRepo)
    monkeypatch.setattr(duplicates_service, "DuplicateGroupRepository", _RecordingDuplicateRepo)
    monkeypatch.setattr(
        duplicates_service,
        "find_gallery_duplicate_groups",
        lambda *args, **kwargs: [_cross_gid_group()],
    )
    groups = await scan_library_cross_gid_groups(_session_factory())

    assert len(groups) == 1
    assert _RecordingDuplicateRepo.calls, "cross-gid scan must persist via duplicate_groups"
    kind, persisted = _RecordingDuplicateRepo.calls[-1]
    assert kind == "cross_gid"
    assert [g["key"] for g in persisted] == ["alice|book"]
    assert not hasattr(state_module.app_state, "cross_gid_duplicates"), (
        "the in-memory snapshot no longer exists (T5.3)"
    )
    assert _FakeSession.last_marker == "duplicates_scan_cross_gid", (
        "a completed scan must persist its ready marker"
    )


@pytest.mark.asyncio
async def test_favorites_scan_persists_groups_not_state(monkeypatch):
    from galleryvault.config import Settings

    group = {
        "key": "alice|book",
        "artist": "alice",
        "items": [
            {
                "gallery_id": 10,
                "gid": 1001,
                "title": "[Alice] Book",
                "posted_at": "2024-01-01T00:00:00+00:00",
            }
        ],
    }

    class _Repo(_FakeFavoritesRepo):
        async def all_items(self):
            # (favcat, gid, token, title, url, gallery_id, ...)
            return [(1, 1001, "tok", "[Alice] Book", "", 10, 1000)]

        async def gallery_titles_by_gid(self, gids):
            return {1001: ("[Alice] Book", None)}

    tm = TaskManager()
    monkeypatch.setattr(favorite_duplicates, "FavoritesRepository", _Repo)
    monkeypatch.setattr(favorite_duplicates, "find_duplicate_groups", lambda *a, **k: [group])
    monkeypatch.setattr(favorite_duplicates, "DuplicateGroupRepository", _RecordingDuplicateRepo)
    monkeypatch.setattr(state_module.app_state, "task_manager", tm)
    monkeypatch.setattr(state_module.app_state, "session_factory", _session_factory())
    monkeypatch.setattr(state_module.app_state, "worker_session_factory", None)
    monkeypatch.setattr(state_module.app_state, "settings", Settings())

    await favorite_duplicates.run_duplicates_scan()

    assert _RecordingDuplicateRepo.calls, "favorites scan must persist via duplicate_groups"
    kind, persisted = _RecordingDuplicateRepo.calls[-1]
    assert kind == "favorites"
    assert [g["key"] for g in persisted] == ["alice|book"]
    assert tm.duplicates_state.get("groups") in (None, []), (
        "tm.duplicates_state must only keep progress"
    )
    assert tm.duplicates_state.get("stage") == "done"


@pytest.mark.asyncio
async def test_refresh_returns_202_without_waiting(monkeypatch):
    route = next(
        r
        for r in duplicates_router.router.routes
        if getattr(r, "path", "") == "/api/library/duplicates/cross-gid/refresh"
    )
    assert route.status_code == 202

    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_scan(session_factory=None):
        started.set()
        await release.wait()
        return []

    monkeypatch.setattr(duplicates_service, "scan_library_cross_gid_groups", slow_scan)
    monkeypatch.setattr(state_module.app_state, "session_factory", _session_factory())

    async def empty_groups(session, kind, *, status=None, present=None):
        return []

    async def not_scanned(session, kind):
        return False

    monkeypatch.setattr(duplicates_router, "list_groups", empty_groups)
    monkeypatch.setattr(duplicates_router, "kind_scanned", not_scanned)

    begin = time.monotonic()
    result = await duplicates_router.refresh_cross_gid_groups(session=object())
    elapsed = time.monotonic() - begin

    assert elapsed < 0.5, f"refresh blocked for {elapsed:.2f}s"
    assert result["ready"] is False

    await asyncio.wait_for(started.wait(), timeout=2)
    assert cross_gid_scan_lock.locked() is True
    with pytest.raises(HTTPException) as excinfo:
        await duplicates_router.refresh_cross_gid_groups(session=object())
    assert excinfo.value.status_code == 409

    release.set()
    for _ in range(200):
        if not cross_gid_scan_lock.locked():
            break
        await asyncio.sleep(0.01)
    assert cross_gid_scan_lock.locked() is False
