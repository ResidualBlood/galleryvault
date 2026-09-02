"""Regression tests for the low-priority review items (L1, L2, L8, L9).

L1: the 422 message on the galleries list endpoint must state the real
    ``page_size`` bound (500).
L2: a manual retry must reset ``max_retries`` to 10, otherwise a task whose
    automatic budget was exhausted (max_retries=0) stays stuck forever.
L8: the first favorite-counts call returns immediately (warmed asynchronously
    at startup) instead of blocking the request loop on a network fetch.
L9: ``existing_rows`` streams a coarse ``storage_path`` prefix prefilter so a
    scan of one root does not pull the whole non-expunged table.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from galleryvault.app import main
from galleryvault.app.routers import downloads, galleries
from galleryvault.db import repository as repo
from galleryvault.services import favorites_worker


@pytest.mark.asyncio
async def test_l1_page_size_message_matches_500_bound() -> None:
    with pytest.raises(HTTPException) as excinfo:
        # The bound check runs before any DB access, so the router function can
        # be driven directly.
        await galleries.gallery_list(page=1, page_size=501)
    assert excinfo.value.status_code == 422
    assert "between 1 and 500" in excinfo.value.detail


class _RetryRow:
    def __init__(self) -> None:
        self.status = "failed"
        self.retry_count = 3
        self.max_retries = 0
        self.retry_at = None
        self.error_message = "boom"
        self.finished_at = None


class _RetrySession:
    def __init__(self, row) -> None:
        self.row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def begin(self):
        return self

    async def get(self, model, pk):
        return self.row


@pytest.mark.asyncio
async def test_l2_manual_retry_resets_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _RetryRow()
    monkeypatch.setattr(main, "_settings_session", lambda: _RetrySession(row))
    monkeypatch.setattr(main, "_download_cancelled", {42})
    result = await downloads.retry_download(42)
    assert result == {"id": 42, "status": "pending"}
    assert row.max_retries == 10
    assert row.retry_count == 0
    assert row.retry_at is None
    assert row.error_message is None
    assert row.finished_at is None
    assert 42 not in main._download_cancelled


@pytest.mark.asyncio
async def test_l8_first_count_call_never_blocks_on_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cold-cache call must not await a fetch: it spawns the refresh and
    returns {} so the request loop is never blocked by a slow ExHentai call."""
    spawned = []

    def fake_spawn(coro, operation):
        spawned.append(operation)
        if hasattr(coro, "close"):
            coro.close()

    monkeypatch.setattr(main, "_spawn", fake_spawn)
    monkeypatch.setattr(favorites_worker, "_fav_counts_cache", {"ts": 0.0, "counts": {}})
    monkeypatch.setattr(main, "_fav_counts_cache", favorites_worker._fav_counts_cache)
    monkeypatch.setattr(main.app.state, "eh_client", object())

    counts = await main._favorite_counts_cached()
    assert counts == {}
    assert spawned == ["favorite counts warmup"]


@pytest.mark.asyncio
async def test_l9_existing_rows_prefilters_by_storage_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The streamed select must constrain storage_path to the roots instead of
    selecting every non-expunged row."""

    captured = {}

    class FakeStream:
        def __init__(self, statement) -> None:
            captured["sql"] = str(
                statement.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
            self._rows = iter(())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._rows)
            except StopIteration:
                raise StopAsyncIteration

    class FakeSession:
        async def stream(self, statement):
            return FakeStream(statement)

    service = repo.GalleryRepository(session=FakeSession())
    await service.existing_rows(["/mnt/library"])

    sql = captured["sql"].lower()
    assert "expunged" in sql
    assert "is false" in sql
    assert "/mnt/library" in sql
    assert " like " in sql
