from types import SimpleNamespace

import pytest

from galleryvault.app.state import app_state
from galleryvault.services.favorites_worker import (
    FavoriteDownloadQueue,
    FavoritesRepositoryProxy,
    _fav_counts_cache,
    _img_data_uri,
    _parse_gdata_tags,
    _unix_to_iso,
    favorite_counts_cached,
)


def test_unix_to_iso():
    assert _unix_to_iso(None) is None
    assert _unix_to_iso("invalid") is None
    res = _unix_to_iso(1600000000)
    assert res is not None
    assert "2020" in res


def test_parse_gdata_tags():
    tags = ["artist:michiking", "group:circle", "female:sole female", "nonamespace"]
    parsed = _parse_gdata_tags(tags)
    assert parsed == [
        ("artist", "michiking"),
        ("group", "circle"),
        ("female", "sole female"),
        ("misc", "nonamespace"),
    ]


def test_img_data_uri():
    assert _img_data_uri(b"") is None
    png_data = b"\x89PNG\r\n\x1a\n" + b"rest"
    assert _img_data_uri(png_data).startswith("data:image/png;base64,")
    jpg_data = b"\xff\xd8\xff\xe0" + b"rest"
    assert _img_data_uri(jpg_data).startswith("data:image/jpeg;base64,")
    gif_data = b"GIF89a" + b"rest"
    assert _img_data_uri(gif_data).startswith("data:image/gif;base64,")


@pytest.mark.asyncio
async def test_favorites_repo_proxy_methods():
    orig_session = app_state.session_factory
    try:
        class FakeRepo:
            def __init__(self, session):
                pass

            async def known_gids(self, favcat):
                return {1, 2}

            async def existing_gallery_gids(self, gids):
                return {1}

            async def remember(self, favcat, item):
                return True

            async def remember_many(self, favcat, items):
                return len(items)

            async def prune(self, favcat, current_gids):
                return 0

            async def checked(self, favcat, success):
                pass

            async def category(self, favcat):
                return SimpleNamespace(favcat=favcat, name="Fav")

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def begin(self):
                return self

        app_state.session_factory = lambda: FakeSession()
        from unittest.mock import patch
        with patch("galleryvault.services.favorites_worker.FavoritesRepository", FakeRepo):
            proxy = FavoritesRepositoryProxy()
            assert await proxy.known_gids(0) == {1, 2}
            assert await proxy.existing_gallery_gids([1, 2, 3]) == {1}
            assert await proxy.remember(0, SimpleNamespace(gid=1)) is True
            assert await proxy.remember_many(0, [SimpleNamespace(gid=1)]) == 1
            assert await proxy.prune(0, {1}) == 0
            assert (await proxy.category(0)).name == "Fav"
    finally:
        app_state.session_factory = orig_session


@pytest.mark.asyncio
async def test_favorite_download_queue():
    orig_session = app_state.session_factory
    try:
        class FakeDownloadRepo:
            def __init__(self, session):
                pass

            async def create(self, gid, token, title, mode, quality=None):
                return SimpleNamespace(id=42)

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def begin(self):
                return self

        app_state.session_factory = lambda: FakeSession()
        from unittest.mock import patch
        with patch("galleryvault.services.favorites_worker.DownloadRepository", FakeDownloadRepo):
            queue = FavoriteDownloadQueue()
            item = SimpleNamespace(gid=123, token="tok", title="Title")
            assert await queue.enqueue(item) is True
    finally:
        app_state.session_factory = orig_session


@pytest.mark.asyncio
async def test_favorite_counts_cached_wait_on_cold_concurrent(monkeypatch):
    call_count = 0

    class FakeEhClient:
        async def fetch_favorite_counts(self):
            nonlocal call_count
            call_count += 1
            import asyncio
            await asyncio.sleep(0.05)
            return {0: 10, 1: 20}

    orig_client = app_state.eh_client
    app_state.eh_client = FakeEhClient()
    _fav_counts_cache["ts"] = 0.0
    _fav_counts_cache["counts"] = {}
    try:
        import asyncio
        results = await asyncio.gather(
            favorite_counts_cached(wait_on_cold=True),
            favorite_counts_cached(wait_on_cold=True),
            favorite_counts_cached(wait_on_cold=True),
        )
        assert call_count == 1
        assert results == [{0: 10, 1: 20}, {0: 10, 1: 20}, {0: 10, 1: 20}]
    finally:
        app_state.eh_client = orig_client
        _fav_counts_cache["ts"] = 0.0
        _fav_counts_cache["counts"] = {}
