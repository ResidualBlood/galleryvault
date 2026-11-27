"""Failure injection for the favorites domain (T9.3a).

Pins two invariants of the split-out favorites modules:

1. A favorites check whose upstream listing never succeeds must not touch the
   local folder rows (no prune, no ``remember``/``favorite_items`` write) and
   must record the failure via ``checked(favcat, False)``.
2. A remote-cover fill whose upstream calls raise ``EhClientError`` must leave
   no temp file behind, remember the miss in the negative cache and release the
   in-flight single-flight slot.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from galleryvault.app.state import app_state
from galleryvault.services.eh_client import EhClientError
from galleryvault.services.favorites import FavoritesService, cover_cache

GID = 1_234_567


class _RecordingRepository:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def category(self, favcat: int) -> SimpleNamespace:
        return SimpleNamespace(favcat=favcat, name="Fav")

    async def known_gids(self, favcat: int) -> set[int]:
        self.calls.append("known_gids")
        return set()

    async def existing_gallery_gids(self, gids: list[int]) -> set[int]:
        self.calls.append("existing_gallery_gids")
        return set()

    async def remember(self, favcat: int, item: object) -> None:
        self.calls.append(("remember", getattr(item, "gid", None)))

    async def remember_many(self, favcat: int, items: list[object]) -> None:
        self.calls.append(("remember_many", len(items)))

    async def forget(self, favcat: int, gids: list[int]) -> int:
        self.calls.append(("forget", tuple(gids)))
        return len(gids)

    async def prune(
        self, favcat: int, current_gids: set[int], allow_empty: bool = False
    ) -> int:
        self.calls.append(("prune", tuple(sorted(current_gids)), allow_empty))
        return 0

    async def checked(self, favcat: int, success: bool) -> None:
        self.calls.append(("checked", success))


class _FailingFetcher:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch_favorites(self, favcat: int, progress: object = None) -> list[object]:
        self.calls += 1
        raise RuntimeError("favorites page unreachable")


@pytest.mark.asyncio
async def test_check_category_fetch_failure_keeps_local_rows_untouched() -> None:
    repo = _RecordingRepository()
    fetcher = _FailingFetcher()
    service = FavoritesService(fetcher, repo)

    with pytest.raises(RuntimeError, match="favorites check failed after 3 attempts"):
        await service.check_category(0, retries=9)

    # ``retries`` is clamped to 3 upstream attempts.
    assert fetcher.calls == 3
    assert ("checked", False) in repo.calls
    # No local state may be written from an unconfirmed listing.
    assert not any(
        call == "known_gids" or isinstance(call, tuple) and call[0] in {"prune", "remember", "remember_many"}
        for call in repo.calls
    ), repo.calls


class _FailingCoverClient:
    def __init__(self) -> None:
        self.calls = 0

    async def download_image(self, url: str) -> bytes:
        self.calls += 1
        raise EhClientError("upstream cover 500")

    async def fetch_gallery_cover(self, gid: int, token: str) -> tuple[bytes, str]:
        self.calls += 1
        raise EhClientError("upstream cover 500")


@pytest.mark.asyncio
async def test_cover_fill_upstream_failure_cleans_up_and_negative_caches(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _FailingCoverClient()
    monkeypatch.setattr(app_state, "eh_client", client)
    monkeypatch.setattr(cover_cache, "_get_background_session_factory", lambda: None)
    monkeypatch.setattr(cover_cache, "REMOTE_COVER_MIN_INTERVAL", 0.0)

    path = await cover_cache.ensure_remote_cover(
        GID,
        "tok",
        cache_dir=tmp_path,
        cached_meta={"thumb": "https://ehgt.org/t/cover.jpg"},
    )
    await asyncio.sleep(0)

    assert path is None
    # No half-written cover or leftover ``.tmp`` file.
    assert list(tmp_path.iterdir()) == []
    # The miss is negative-cached and the single-flight slot is released.
    assert cover_cache._cover_neg_get(GID) is True
    assert cover_cache._cover_inflight == {}

    # A retry inside the TTL is answered from the negative cache.
    again = await cover_cache.ensure_remote_cover(
        GID, "tok", cache_dir=tmp_path, cached_meta={"thumb": "https://ehgt.org/t/cover.jpg"}
    )
    assert again is None
    assert client.calls == 2
