"""Regression tests for the B1-B2 favorites/tag-sync batch.

Covers: prune truncation guard + allow_empty semantics, remember_many batch
dedupe, tag sync category refresh passing a session to ``refresh_gdata``,
bounded cover downloads, and the empty favorite-count cache.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import column

from galleryvault.app.state import app_state
from galleryvault.db.repositories import favorites as favorites_repo_module
from galleryvault.db.repositories.favorites import FavoritesRepository
from galleryvault.services import favorites_worker
from galleryvault.services import tag_sync_worker as tag_worker


class _Result:
    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount


class _FakeSession:
    """Minimal AsyncSession stand-in: records executed statements."""

    def __init__(self, recorded: int = 0, rowcount: int = 1) -> None:
        self._recorded = recorded
        self._rowcount = rowcount
        self.statements: list[Any] = []
        self.flush_count = 0

    async def scalar(self, stmt: Any) -> int:
        return self._recorded

    async def execute(self, stmt: Any) -> _Result:
        self.statements.append(stmt)
        return _Result(self._rowcount)

    async def flush(self) -> None:
        self.flush_count += 1

    def add(self, obj: Any) -> None:  # pragma: no cover - not used here
        pass


# --------------------------------------------------------------------------
# P2-1 prune: truncation guard + allow_empty
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prune_skips_listing_that_looks_truncated(caplog):
    session = _FakeSession(recorded=300, rowcount=250)
    repo = FavoritesRepository(session)  # type: ignore[arg-type]

    # First page only (100 of 300 recorded rows) -> pagination likely broke.
    removed = await repo.prune(0, set(range(100)))

    assert removed == 0
    assert session.statements == []
    assert any("looks truncated" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_prune_runs_when_listing_covers_most_rows():
    session = _FakeSession(recorded=100, rowcount=7)
    repo = FavoritesRepository(session)  # type: ignore[arg-type]

    removed = await repo.prune(3, set(range(100)))

    assert removed == 7
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_prune_small_folder_is_never_guarded():
    session = _FakeSession(recorded=10, rowcount=8)
    repo = FavoritesRepository(session)  # type: ignore[arg-type]

    # 10 recorded rows, listing has 2: below the minimum size, prune normally.
    assert await repo.prune(1, {1, 2}) == 8
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_prune_empty_listing_requires_allow_empty():
    session = _FakeSession(recorded=42, rowcount=42)
    repo = FavoritesRepository(session)  # type: ignore[arg-type]

    assert await repo.prune(2, set()) == 0
    assert session.statements == []

    assert await repo.prune(2, set(), allow_empty=True) == 42
    assert len(session.statements) == 1


# --------------------------------------------------------------------------
# P3-8 remember_many: batch-internal dedupe
# --------------------------------------------------------------------------


class _FakeInsert:
    def __init__(self, rows: list[dict[str, Any]], captured: list[list[dict[str, Any]]]) -> None:
        self.rows = rows
        captured.append(rows)
        self.excluded = SimpleNamespace(
            **{key: column(key) for key in ("token", "title", "url", "thumb", "note", "last_seen_at")}
        )

    def on_conflict_do_update(self, **_kwargs: Any) -> _FakeInsert:
        return self


class _FakeInsertFactory:
    def __init__(self, captured: list[list[dict[str, Any]]]) -> None:
        self._captured = captured

    def values(self, rows: list[dict[str, Any]]) -> _FakeInsert:
        return _FakeInsert(rows, self._captured)


@pytest.mark.asyncio
async def test_remember_many_dedupes_duplicate_gids_in_batch():
    captured: list[list[dict[str, Any]]] = []
    session = _FakeSession()
    repo = FavoritesRepository(session)  # type: ignore[arg-type]

    class _Item:
        def __init__(self, gid: int, title: str) -> None:
            self.gid = gid
            self.token = f"tok{gid}"
            self.title = title
            self.url = f"https://e-hentai.org/g/{gid}/tok{gid}/"

    items = [_Item(1, "old"), _Item(2, "keep"), _Item(1, "new")]

    with patch.object(
        favorites_repo_module, "pg_insert", lambda _table: _FakeInsertFactory(captured)
    ):
        await repo.remember_many(0, items)

    assert len(captured) == 1
    rows = captured[0]
    assert [row["gid"] for row in rows] == [1, 2]
    # Last occurrence wins, matching dict-last-wins semantics.
    assert rows[0]["title"] == "new"


# --------------------------------------------------------------------------
# P2-2 tag sync category refresh must pass the session to refresh_gdata
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_category_refresh_passes_session_to_refresh_gdata():
    received: list[Any] = []
    refreshed: dict[int, str] = {}

    async def fake_refresh_gdata(session, pairs, client=None, force=False):
        received.append(session)
        assert sorted(pairs) == [(101, "tok101")]
        return {101: {"category": "Manga", "expunged": False}}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def execute(self, _stmt):
            class _Res:
                def all(self):
                    return [(1, 101, "tok101")]

            return _Res()

    class FakeRepo:
        def __init__(self, _session):
            pass

        async def pending_category_refresh_ids(self, _limit, last_id):
            return [1] if last_id == 0 else []

        async def refresh_category(self, gal_id, category):
            refreshed[gal_id] = category

    orig_factory = app_state.session_factory
    orig_client = app_state.eh_client
    try:
        app_state.session_factory = lambda: FakeSession()
        app_state.eh_client = object()
        with (
            patch.object(tag_worker, "GalleryRepository", FakeRepo),
            patch.object(tag_worker, "refresh_gdata", fake_refresh_gdata),
        ):
            count = await tag_worker.category_refresh_once()
    finally:
        app_state.session_factory = orig_factory
        app_state.eh_client = orig_client
        if app_state.task_manager:
            app_state.task_manager.tag_sync_state["category_refresh_running"] = False

    assert count == 1
    assert refreshed == {1: "Manga"}
    assert len(received) == 1
    assert isinstance(received[0], FakeSession)


# --------------------------------------------------------------------------
# P2-10 bounded cover download fan-out
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remote_cover_data_batch_bounds_concurrency(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0
            self.calls = 0

        async def download_image(self, _url: str) -> bytes:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                await asyncio.sleep(0.005)
                return b"\xff\xd8\xffcover"
            finally:
                self.active -= 1

    client = FakeClient()
    monkeypatch.setattr(favorites_worker, "_remote_cover_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(app_state, "eh_client", client, raising=False)

    pairs = [(gid, f"tok{gid}") for gid in range(1, 61)]
    metadata = {gid: {"thumb": f"https://thumb/{gid}"} for gid, _ in pairs}

    result = await favorites_worker.remote_cover_data_batch(
        pairs, metadata, download=True, encode=False
    )

    assert client.calls == 60
    assert result == {}
    assert client.max_active <= favorites_worker._COVER_HEAL_CHUNK


# --------------------------------------------------------------------------
# P3-9 empty favorite counts are cached briefly
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_favorite_counts_are_cached(monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        async def fetch_favorite_counts(self) -> dict[int, int]:
            calls["n"] += 1
            return {}

    monkeypatch.setattr(favorites_worker.app_state, "eh_client", FakeClient(), raising=False)
    monkeypatch.setattr(favorites_worker, "_fav_counts_cache", {"ts": 0.0, "counts": {}})
    monkeypatch.setattr(favorites_worker, "_fav_counts_refresh_task", None)

    assert await favorites_worker.favorite_counts_cached(wait_on_cold=True) == {}
    assert calls["n"] == 1

    # Second call inside the short empty-result TTL must not refetch.
    assert await favorites_worker.favorite_counts_cached(wait_on_cold=True) == {}
    assert calls["n"] == 1
