"""T10: cross-gid dedup service must narrow queries, thread the clustering and own the lock."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from galleryvault.db.repositories.favorites import FavoritesRepository
from galleryvault.services import duplicates as duplicates_service
from galleryvault.services.duplicates import (
    cross_gid_scan_lock,
    scan_library_cross_gid_duplicates,
    scan_library_cross_gid_duplicates_locked,
)


class _Rows(list):
    def all(self):
        return list(self)


class _FakeRepo:
    def __init__(self, session):
        self.session = session

    async def artist_tags_for_gallery_ids(self, gallery_ids):
        return {}

    async def ignored_duplicate_keys(self):
        return set()

    async def ignored_duplicates(self):
        return []


class _CapturingSession:
    def __init__(self, galleries=(), favorites=()):
        self._galleries = list(galleries)
        self._favorites = list(favorites)
        self.statements: list = []

    async def scalars(self, stmt):
        self.statements.append(stmt)
        if "favorite_items" in str(stmt):
            return _Rows(self._favorites)
        return _Rows(self._galleries)


def _session_factory(session):
    class _Factory:
        def __call__(self):
            class _Ctx:
                async def __aenter__(self):
                    return session

                async def __aexit__(self, *args):
                    return False

            return _Ctx()

    return _Factory()


def _gallery(gid: int, title: str, gallery_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=gallery_id,
        gid=gid,
        title=title,
        title_jpn=None,
        file_size=1024,
        page_count=10,
        file_count=10,
        category="Manga",
        storage_path=f"/lib/{gid}",
        storage_type="folder",
        token="tok",
    )


@pytest.mark.asyncio
async def test_artist_tag_query_filters_namespace():
    class _TagSession:
        def __init__(self):
            self.stmt = None

        async def execute(self, stmt):
            self.stmt = stmt
            return [(7, "alice")]

    session = _TagSession()
    repo = FavoritesRepository(session)

    tag_map = await repo.artist_tags_for_gallery_ids([7])

    sql = str(session.stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "tags.namespace = 'artist'" in sql
    assert tag_map == {7: [("artist", "alice")]}


@pytest.mark.asyncio
async def test_scan_select_omits_source_meta(monkeypatch):
    session = _CapturingSession()
    monkeypatch.setattr("galleryvault.db.repository.FavoritesRepository", _FakeRepo)

    await scan_library_cross_gid_duplicates(_session_factory(session))

    gallery_stmts = [str(stmt) for stmt in session.statements if "FROM galleries" in str(stmt)]
    assert gallery_stmts, "service must query the galleries table"
    assert all("source_meta" not in sql for sql in gallery_stmts)
    assert all("galleries.title" in sql for sql in gallery_stmts)

    favorite_stmts = [
        str(stmt) for stmt in session.statements if "FROM favorite_items" in str(stmt)
    ]
    assert favorite_stmts
    assert all("favorite_items.note" not in sql for sql in favorite_stmts)


@pytest.mark.asyncio
async def test_clustering_runs_off_event_loop_thread(monkeypatch):
    session = _CapturingSession(
        galleries=[
            _gallery(1001, "[Alice] My Book", 10),
            _gallery(1002, "[Alice] My Book [DL版]", 11),
        ]
    )
    monkeypatch.setattr("galleryvault.db.repository.FavoritesRepository", _FakeRepo)

    seen: dict[str, object] = {}

    def fake_find(candidates, *, tag_map=None, fav_gids=None):
        seen["ident"] = threading.get_ident()
        seen["candidates"] = candidates
        return []

    monkeypatch.setattr(duplicates_service, "find_gallery_duplicate_groups", fake_find)

    await scan_library_cross_gid_duplicates(_session_factory(session))

    assert seen["ident"] != threading.get_ident(), "clustering must not run on the event loop"
    candidates = seen["candidates"]
    assert len(candidates) == 2
    assert all(isinstance(c, dict) for c in candidates)


@pytest.mark.asyncio
async def test_locked_scan_wait_false_returns_none_while_running(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_scan(session_factory=None):
        started.set()
        await release.wait()
        return [{"key": "k"}]

    monkeypatch.setattr(duplicates_service, "scan_library_cross_gid_duplicates", slow_scan)

    assert cross_gid_scan_lock.locked() is False
    first = asyncio.create_task(
        scan_library_cross_gid_duplicates_locked(None, wait=False)
    )
    try:
        await started.wait()
        assert cross_gid_scan_lock.locked() is True
        second = await scan_library_cross_gid_duplicates_locked(None, wait=False)
        assert second is None
    finally:
        release.set()

    assert await first == [{"key": "k"}]
    assert cross_gid_scan_lock.locked() is False
