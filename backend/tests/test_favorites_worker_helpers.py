from types import SimpleNamespace

import pytest

from galleryvault.app.state import app_state
from galleryvault.services.favorites_worker import (
    FavoriteDownloadQueue,
    FavoritesRepositoryProxy,
    _cover_cache_file,
    _cover_cache_write_path,
    _fav_counts_cache,
    _img_data_uri,
    _parse_gdata_tags,
    _unix_to_iso,
    favorite_counts_cached,
    remote_cover_data_batch,
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


def test_parse_gdata_tags_accepts_metadata_map_dicts():
    parsed = _parse_gdata_tags(
        [
            {"namespace": "artist", "name": "alice"},
            {"namespace": "misc", "name": "twintails"},
            {"namespace": "", "name": ""},
            ["language", "chinese"],
            ("group", "circle"),
            "female:sole female",
            "nonamespace",
            None,
            123,
        ]
    )
    assert parsed == [
        ("artist", "alice"),
        ("misc", "twintails"),
        ("language", "chinese"),
        ("group", "circle"),
        ("female", "sole female"),
        ("misc", "nonamespace"),
    ]


def test_cover_cache_file_prefers_img(tmp_path):
    gid = 42
    jpg = tmp_path / f"{gid}.jpg"
    img = tmp_path / f"{gid}.img"
    jpg.write_bytes(b"jpg")
    assert _cover_cache_file(tmp_path, gid) == jpg
    img.write_bytes(b"img")
    assert _cover_cache_file(tmp_path, gid) == img
    assert _cover_cache_write_path(tmp_path, gid) == img
    assert _cover_cache_file(tmp_path, 99) is None


@pytest.mark.asyncio
async def test_remote_cover_batch_uses_img_or_jpg_without_download(tmp_path, monkeypatch):
    from galleryvault.services import favorites_worker as fw

    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)
    (tmp_path / "1.img").write_bytes(b"\xff\xd8\xff" + b"a" * 8)
    (tmp_path / "2.jpg").write_bytes(b"\x89PNG\r\n\x1a\n")
    orig = app_state.eh_client
    app_state.eh_client = object()
    try:
        result = await remote_cover_data_batch(
            [(1, "tok"), (2, "tok"), (3, "tok")],
            {1: {"thumb": "http://x/1"}, 2: {"thumb": "http://x/2"}, 3: {"thumb": "http://x/3"}},
            download=False,
        )
        assert 1 in result and result[1].startswith("data:image/jpeg")
        assert 2 in result and result[2].startswith("data:image/png")
        assert 3 not in result
        assert not (tmp_path / "3.img").exists()
    finally:
        app_state.eh_client = orig


@pytest.mark.asyncio
async def test_remote_cover_batch_writes_img_not_jpg(tmp_path, monkeypatch):
    from galleryvault.services import favorites_worker as fw

    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)
    downloaded = []

    class Client:
        async def download_image(self, url):
            downloaded.append(url)
            return b"\xff\xd8\xff" + b"x" * 20

    orig = app_state.eh_client
    app_state.eh_client = Client()
    try:
        result = await remote_cover_data_batch(
            [(9, "tok")],
            {9: {"thumb": "http://ehgt.org/9"}},
            download=True,
            encode=False,
        )
        assert result == {}
        assert downloaded == ["http://ehgt.org/9"]
        assert (tmp_path / "9.img").is_file()
        assert not (tmp_path / "9.jpg").exists()
    finally:
        app_state.eh_client = orig


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

            async def create(self, gid, token, title, mode, quality=None, title_jpn=None):
                return SimpleNamespace(id=42)

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def begin(self):
                return self

        app_state.session_factory = lambda: FakeSession()
        attached = []

        class FakeUpdatesRepo:
            def __init__(self, session):
                pass

            async def attach_download(self, new_gid, task_id):
                attached.append((new_gid, task_id))
                return 1

        from unittest.mock import patch
        with patch("galleryvault.services.favorites_worker.DownloadRepository", FakeDownloadRepo), patch(
            "galleryvault.services.favorites_worker.GalleryUpdatesRepository", FakeUpdatesRepo
        ):
            queue = FavoriteDownloadQueue()
            item = SimpleNamespace(gid=123, token="tok", title="Title")
            assert await queue.enqueue(item) is True
            assert attached == [(123, 42)]
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


@pytest.mark.asyncio
async def test_favorite_counts_cached_cancelled_caller_shares_task():
    call_count = 0

    class FakeEhClient:
        async def fetch_favorite_counts(self):
            nonlocal call_count
            call_count += 1
            import asyncio
            await asyncio.sleep(0.08)
            return {0: 99}

    orig_client = app_state.eh_client
    app_state.eh_client = FakeEhClient()
    _fav_counts_cache["ts"] = 0.0
    _fav_counts_cache["counts"] = {}
    try:
        import asyncio

        # Start caller 1 and cancel it midway
        t1 = asyncio.create_task(favorite_counts_cached(wait_on_cold=True))
        await asyncio.sleep(0.01)
        t1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t1

        # Caller 2 starts before the background task completes, should share the task
        res2 = await favorite_counts_cached(wait_on_cold=True)
        assert res2 == {0: 99}
        assert call_count == 1
    finally:
        app_state.eh_client = orig_client
        _fav_counts_cache["ts"] = 0.0
        _fav_counts_cache["counts"] = {}


@pytest.mark.asyncio
async def test_favorite_size_sync_heals_missing_covers(tmp_path, monkeypatch):
    from galleryvault.services import favorites_worker as fw
    from galleryvault.services.favorites_worker import favorite_size_sync

    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)
    (tmp_path / "2.img").write_bytes(b"cached")
    downloaded: list[str] = []

    class Client:
        async def fetch_gmetadata(self, pairs):
            return {}

        async def download_image(self, url):
            downloaded.append(url)
            return b"\xff\xd8\xff" + b"x" * 20

    class FavRepo:
        def __init__(self, session):
            pass

        async def all_gids_for_favcat(self, favcat):
            return [
                (1, "tok1", "http://ehgt.org/1"),
                (2, "tok2", "http://ehgt.org/2"),
                (3, "tok3", None),
            ]

        async def set_file_size(self, *args, **kwargs):
            pass

    class GalRepo:
        def __init__(self, session):
            pass

        async def seed_metadata_from_galleries(self, favcat):
            return 0

        async def metadata_map(self, gids):
            return {}

        async def null_image_quality_gids(self, gids):
            return set()

        async def upsert_metadata(self, entries):
            return 0

        async def storage_size_map(self, gids):
            return {}

        async def set_image_qualities(self, mapping):
            return 0

        async def apply_metadata_to_galleries(self, favcat, limit=200):
            return 0

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def begin(self):
            return self

    orig_factory = app_state.session_factory
    orig_client = app_state.eh_client
    try:
        app_state.session_factory = lambda: Session()
        app_state.eh_client = Client()
        monkeypatch.setattr(fw, "FavoritesRepository", FavRepo)
        monkeypatch.setattr(fw, "GalleryRepository", GalRepo)
        fw._size_sync_inflight.clear()
        await favorite_size_sync(4)
        assert downloaded == ["http://ehgt.org/1"]
        assert (tmp_path / "1.img").is_file()
        assert not (tmp_path / "3.img").exists()
    finally:
        app_state.session_factory = orig_factory
        app_state.eh_client = orig_client
        fw._size_sync_inflight.clear()


@pytest.mark.asyncio
async def test_favorite_size_sync_applies_metadata_infers_quality_and_records_history(
    tmp_path, monkeypatch
):
    from galleryvault.services import favorites_worker as fw
    from galleryvault.services.favorites_worker import favorite_size_sync

    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)
    qualities: dict[int, str] = {}
    applied_calls: list[int] = []

    class Client:
        async def fetch_gmetadata(self, pairs):
            return {int(gid): {"file_size": 1000, "thumb": ""} for gid, _tok in pairs}

        async def download_image(self, url):
            return b""

    class FavRepo:
        def __init__(self, session):
            pass

        async def all_gids_for_favcat(self, favcat):
            return [(10, "tok", None)]

        async def set_file_size(self, *args, **kwargs):
            pass

    class GalRepo:
        def __init__(self, session):
            pass

        async def seed_metadata_from_galleries(self, favcat):
            return 0

        async def metadata_map(self, gids):
            return {}

        async def null_image_quality_gids(self, gids):
            return set()

        async def upsert_metadata(self, entries):
            return len(entries)

        async def storage_size_map(self, gids):
            return {10: (950, None)}

        async def set_image_qualities(self, mapping):
            qualities.update(mapping)
            return len(mapping)

        async def apply_metadata_to_galleries(self, favcat, limit=200):
            applied_calls.append(limit)
            return 3 if len(applied_calls) == 1 else 0

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def begin(self):
            return self

    orig_factory = app_state.session_factory
    orig_client = app_state.eh_client
    tm = app_state.task_manager
    before = len(tm.task_history)
    try:
        app_state.session_factory = lambda: Session()
        app_state.eh_client = Client()
        monkeypatch.setattr(fw, "FavoritesRepository", FavRepo)
        monkeypatch.setattr(fw, "GalleryRepository", GalRepo)
        fw._size_sync_inflight.clear()
        tm.metadata_sync_state["history_recorded"] = False
        await favorite_size_sync(1)
        assert qualities == {10: "original"}
        assert applied_calls == [200, 200]
        assert tm.task_history[0]["task"] == "metadata"
        assert tm.task_history[0]["status"] == "success"
        assert len(tm.task_history) == before + 1
    finally:
        app_state.session_factory = orig_factory
        app_state.eh_client = orig_client
        fw._size_sync_inflight.clear()
        if tm.task_history and tm.task_history[0].get("task") == "metadata":
            tm.task_history.pop(0)


@pytest.mark.asyncio
async def test_favorite_size_sync_fetches_gdata_when_seeded_metadata_lacks_file_size(
    tmp_path, monkeypatch
):
    from galleryvault.services import favorites_worker as fw
    from galleryvault.services.favorites_worker import favorite_size_sync

    monkeypatch.setattr(fw, "_remote_cover_cache_dir", lambda: tmp_path)
    fetched_pairs: list[tuple[int, str]] = []
    qualities: dict[int, str] = {}

    class Client:
        async def fetch_gmetadata(self, pairs):
            fetched_pairs.extend((int(gid), tok) for gid, tok in pairs)
            return {int(gid): {"file_size": 1000, "thumb": ""} for gid, tok in pairs}

        async def download_image(self, url):
            return b""

    class FavRepo:
        def __init__(self, session):
            pass

        async def all_gids_for_favcat(self, favcat):
            return [(10, "tok", None)]

        async def set_file_size(self, *args, **kwargs):
            pass

    class GalRepo:
        def __init__(self, session):
            pass

        async def seed_metadata_from_galleries(self, favcat):
            return 1

        async def metadata_map(self, gids):
            return {10: {"file_size": None, "title": "seeded"}}

        async def null_image_quality_gids(self, gids):
            return {10}

        async def upsert_metadata(self, entries):
            return len(entries)

        async def storage_size_map(self, gids):
            return {10: (950, None)}

        async def set_image_qualities(self, mapping):
            qualities.update(mapping)
            return len(mapping)

        async def apply_metadata_to_galleries(self, favcat, limit=200):
            return 0

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def begin(self):
            return self

    orig_factory = app_state.session_factory
    orig_client = app_state.eh_client
    tm = app_state.task_manager
    try:
        app_state.session_factory = lambda: Session()
        app_state.eh_client = Client()
        monkeypatch.setattr(fw, "FavoritesRepository", FavRepo)
        monkeypatch.setattr(fw, "GalleryRepository", GalRepo)
        fw._size_sync_inflight.clear()
        tm.metadata_sync_state["history_recorded"] = False
        await favorite_size_sync(1)
        assert fetched_pairs == [(10, "tok")]
        assert qualities == {10: "original"}
    finally:
        app_state.session_factory = orig_factory
        app_state.eh_client = orig_client
        fw._size_sync_inflight.clear()
        if tm.task_history and tm.task_history[0].get("task") == "metadata":
            tm.task_history.pop(0)
