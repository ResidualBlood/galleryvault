"""R2 batch-1: favorites/metadata integrity regressions.

Covers review 02-eh-consistency:
- P2-8  ``upsert_metadata`` must not overwrite cached metadata with ``None``
- P2-1  a genuinely empty cloud folder is pruned, while a failed parse and a
        truncated pagination leave local records alone
- P3-9  empty favorite counts are cached briefly but never mean "confirmed 0"
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.services import favorites_worker
from galleryvault.services.eh_client import (
    EhClient,
    FavoriteData,
    FavoriteItems,
    _parse_favorite_counts,
)
from galleryvault.services.favorites import FavoritesService

# --------------------------------------------------------------------------
# P2-8 upsert_metadata keeps cached values when the new value is None
# --------------------------------------------------------------------------


class _RecordSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> SimpleNamespace:
        self.statements.append(statement)
        return SimpleNamespace(rowcount=1)


async def test_upsert_metadata_coalesces_partial_payload_over_cached_values():
    session = _RecordSession()
    repo = GalleryRepository(session)  # type: ignore[arg-type]

    await repo.upsert_metadata([{"gid": 1, "title": None, "posted_at": None, "file_size": None}])

    assert len(session.statements) == 1
    sql = str(session.statements[0].compile(dialect=postgresql.dialect())).lower()

    # SET keeps the stored value when the payload is NULL (only fills empty rows).
    assert "coalesce(excluded.title, gallery_metadata.title)" in sql
    assert "coalesce(excluded.posted_at, gallery_metadata.posted_at)" in sql
    assert "coalesce(excluded.file_size, gallery_metadata.file_size)" in sql
    # Empty tag lists are "unknown", not "remove all tags".
    assert "jsonb_array_length(excluded.tags)" in sql
    # The change-detection WHERE compares the coalesced value, so a payload that
    # only repeats the stored values does not bump updated_at.
    assert (
        "gallery_metadata.title is distinct from coalesce(excluded.title, gallery_metadata.title)"
        in sql
    )


# --------------------------------------------------------------------------
# P2-1 / P3-9: parse failure vs confirmed zero
# --------------------------------------------------------------------------


def test_parse_favorite_counts_distinguishes_zero_from_parse_failure():
    zero = (
        '<div class="fp" onclick="document.location=\'/favorites.php?favcat=0\'">'
        "<div>0</div><div>0 New items</div></div>"
    )
    assert _parse_favorite_counts(zero) == {0: 0}
    assert _parse_favorite_counts("<html><body>login wall</body></html>") is None


def _client(handler: Any) -> EhClient:
    http_client = httpx.AsyncClient(
        base_url="https://exhentai.org",
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    return EhClient(client=http_client)


def _fp(favcat: int, count: int) -> str:
    return (
        f'<div class="fp" onclick="document.location=\'/favorites.php?favcat={favcat}\'">'
        f"<div>{count}</div><div>{favcat} Folder</div></div>"
    )


@pytest.mark.asyncio
async def test_fetch_favorites_marks_empty_folder_confirmed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_fp(0, 0))

    client = _client(handler)
    try:
        items = await client.fetch_favorites(0)
    finally:
        await client.aclose()

    assert isinstance(items, FavoriteItems)
    assert items == []
    assert items.confirmed_empty is True
    assert items.truncated is False
    assert items.cloud_count == 0


@pytest.mark.asyncio
async def test_fetch_favorites_without_header_is_not_confirmed_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        # Valid favorites page whose gallery markup no longer parses.
        return httpx.Response(200, text="<html><body>favorites</body></html>")

    client = _client(handler)
    try:
        items = await client.fetch_favorites(0)
    finally:
        await client.aclose()

    assert items == []
    assert items.confirmed_empty is False
    assert items.cloud_count is None


@pytest.mark.asyncio
async def test_fetch_favorites_flags_listing_short_of_header_count():
    body = _fp(0, 5) + '<a href="/g/1000/aaaaaa/">First</a>'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    client = _client(handler)
    try:
        items = await client.fetch_favorites(0)
    finally:
        await client.aclose()

    assert [item.gid for item in items] == [1000]
    assert items.truncated is True
    assert items.confirmed_empty is False


@pytest.mark.asyncio
async def test_fetch_favorite_counts_returns_none_when_header_is_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>favorites</body></html>")

    client = _client(handler)
    try:
        assert await client.fetch_favorite_counts() is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_empty_favorite_counts_cache_does_not_mean_zero(monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        async def fetch_favorite_counts(self) -> dict[int, int] | None:
            calls["n"] += 1
            return None

    monkeypatch.setattr(favorites_worker.app_state, "eh_client", FakeClient(), raising=False)
    monkeypatch.setattr(favorites_worker, "_fav_counts_cache", {"ts": 0.0, "counts": {}})
    monkeypatch.setattr(favorites_worker, "_fav_counts_refresh_task", None)

    assert await favorites_worker.favorite_counts_cached(wait_on_cold=True) == {}
    # Unknown is cached under the short TTL, and never stored as a zero mapping.
    assert favorites_worker._fav_counts_cache["counts"] is None
    assert await favorites_worker.favorite_counts_cached(wait_on_cold=True) == {}
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_failed_favorite_counts_refresh_is_cached_briefly(monkeypatch):
    calls = {"n": 0}

    class FailingClient:
        async def fetch_favorite_counts(self) -> dict[int, int] | None:
            calls["n"] += 1
            raise RuntimeError("login wall")

    monkeypatch.setattr(favorites_worker.app_state, "eh_client", FailingClient(), raising=False)
    monkeypatch.setattr(favorites_worker, "_fav_counts_cache", {"ts": 0.0, "counts": None})
    monkeypatch.setattr(favorites_worker, "_fav_counts_refresh_task", None)

    assert await favorites_worker.favorite_counts_cached(wait_on_cold=True) == {}
    assert await favorites_worker.favorite_counts_cached(wait_on_cold=True) == {}
    assert calls["n"] == 1
    assert favorites_worker._fav_counts_cache["counts"] is None


# --------------------------------------------------------------------------
# P2-1 service: prune only when the cloud listing can be trusted
# --------------------------------------------------------------------------


class _FakeRepo:
    def __init__(self) -> None:
        self.prune_calls: list[tuple[set[int], bool]] = []

    async def category(self, favcat: int) -> Any:
        return SimpleNamespace(name="Folder")

    async def known_gids(self, favcat: int) -> set[int]:
        return set()

    async def existing_gallery_gids(self, gids: list[int]) -> set[int]:
        return set()

    async def remember_many(self, favcat: int, items: list[Any]) -> int:
        return len(items)

    async def prune(
        self, favcat: int, current_gids: set[int], allow_empty: bool = False
    ) -> int:
        self.prune_calls.append((set(current_gids), allow_empty))
        return 0

    async def checked(self, favcat: int, success: bool) -> None:
        pass


class _FakeFetcher:
    def __init__(self, items: FavoriteItems) -> None:
        self.items = items

    async def fetch_favorites(self, favcat: int, progress: Any = None) -> FavoriteItems:
        return self.items


def _item(gid: int) -> FavoriteData:
    return FavoriteData(gid=gid, token=f"tok{gid}", title=f"G{gid}", url=f"/g/{gid}/")


def _listing(items: list[FavoriteData], **flags: Any) -> FavoriteItems:
    listing = FavoriteItems(items)
    for key, value in flags.items():
        setattr(listing, key, value)
    return listing


@pytest.mark.asyncio
async def test_confirmed_empty_folder_prunes_all_local_records():
    repo = _FakeRepo()
    listing = _listing([], confirmed_empty=True, cloud_count=0)
    service = FavoritesService(fetcher=_FakeFetcher(listing), repository=repo)

    result = await service.check_category(0)

    assert result.found == 0
    assert repo.prune_calls == [(set(), True)]


@pytest.mark.asyncio
async def test_unknown_empty_listing_does_not_prune():
    repo = _FakeRepo()
    service = FavoritesService(fetcher=_FakeFetcher(_listing([])), repository=repo)

    await service.check_category(0)

    assert repo.prune_calls == [(set(), False)]


@pytest.mark.asyncio
async def test_truncated_listing_does_not_prune_at_all():
    repo = _FakeRepo()
    listing = _listing([_item(1)], cloud_count=5, truncated=True)
    service = FavoritesService(fetcher=_FakeFetcher(listing), repository=repo)

    await service.check_category(0)

    assert repo.prune_calls == []


@pytest.mark.asyncio
async def test_small_cloud_removal_still_prunes_normally():
    repo = _FakeRepo()
    listing = _listing([_item(1), _item(2), _item(3)], cloud_count=3)
    service = FavoritesService(fetcher=_FakeFetcher(listing), repository=repo)

    await service.check_category(0)

    assert repo.prune_calls == [({1, 2, 3}, False)]
