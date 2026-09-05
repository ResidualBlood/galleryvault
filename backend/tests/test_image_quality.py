"""Image-quality tracking: inference, superseded-copy cleanup, endpoints.

Covers the original-upgrade feature: the ``image_quality`` inference from
local size vs the ExHentai original size, the automatic removal of the old
resampled copy after an original download, and the gallery-detail download
endpoint (page-by-page and archive forms).
"""

from types import SimpleNamespace

import pytest

from galleryvault.app.routers.galleries import (
    DownloadOriginalRequest,
    download_gallery_original,
    gallery_detail,
)
from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.scanners.base import GalleryMeta
from galleryvault.services import download_worker
from galleryvault.services.deletion import remove_superseded_copy
from galleryvault.services.download_worker import (
    infer_image_quality,
    ingest_downloaded_gallery,
)


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


# --- inference --------------------------------------------------------------


def test_infer_image_quality_original_when_close_to_original_size():
    assert infer_image_quality(1000, 1100) == "original"
    assert infer_image_quality(935, 1000) == "original"  # ratio 0.935


def test_infer_image_quality_resample_when_smaller():
    assert infer_image_quality(500, 1000) == "resample"
    assert infer_image_quality(840, 1000) == "resample"  # ratio 0.84


def test_infer_image_quality_cbz_uses_looser_threshold():
    assert infer_image_quality(820, 1000, "cbz") == "original"  # 0.82
    assert infer_image_quality(790, 1000, "cbz") == "resample"
    # A non-cbz copy at the same ratio is still resample.
    assert infer_image_quality(820, 1000, "ehviewer_dir") == "resample"


def test_infer_image_quality_returns_none_without_data():
    assert infer_image_quality(None, 1000) is None
    assert infer_image_quality(1000, None) is None
    assert infer_image_quality(0, 1000) is None


# --- superseded-copy removal ------------------------------------------------


@pytest.fixture(autouse=True)
def _scan_roots_isolated(monkeypatch, tmp_path):
    from galleryvault.app import dependencies

    monkeypatch.setattr(dependencies, "get_scan_roots", lambda: [str(tmp_path)])


def _result(path, pages=2, quality="original"):
    return SimpleNamespace(gid=7, path=path, pages=pages, quality=quality)


async def test_remove_superseded_copy_deletes_matching_old_dir(tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    (old / "00000001.jpg").write_bytes(b"x")
    new = tmp_path / "new"
    new.mkdir()
    await remove_superseded_copy(_result(str(new), pages=2), old, 2)
    assert not old.exists()


async def test_remove_superseded_copy_keeps_on_page_mismatch(tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    (old / "00000001.jpg").write_bytes(b"x")
    new = tmp_path / "new"
    new.mkdir()
    await remove_superseded_copy(_result(str(new), pages=3), old, 2)
    assert old.exists()


async def test_remove_superseded_copy_keeps_when_same_path(tmp_path):
    new = tmp_path / "new"
    new.mkdir()
    (new / "00000001.jpg").write_bytes(b"x")
    await remove_superseded_copy(_result(str(new), pages=2), new, 2)
    assert new.exists()


async def test_remove_superseded_copy_unlinks_single_file(tmp_path):
    old = tmp_path / "old.cbz"
    old.write_bytes(b"archive")
    new = tmp_path / "new"
    new.mkdir()
    await remove_superseded_copy(_result(str(new), pages=2), old, 2)
    assert not old.exists()


async def test_remove_superseded_copy_is_best_effort_on_errors(tmp_path, monkeypatch):
    import shutil

    old = tmp_path / "old"
    old.mkdir()
    new = tmp_path / "new"
    new.mkdir()

    def _boom(_target):
        raise PermissionError("read-only mount")

    monkeypatch.setattr(shutil, "rmtree", _boom)
    await remove_superseded_copy(_result(str(new), pages=2), old, 2)
    assert old.exists()


# --- ingest marking ---------------------------------------------------------


class _FakeSession:
    """Minimal settings-session double for ingest_downloaded_gallery."""

    def __init__(self, prev_row):
        self._prev = prev_row
        self.ingested = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def begin(self):
        return self

    async def scalar(self, _stmt):
        return self._prev

    async def execute(self, _stmt):
        return _Res([])


class _FakeScanner:
    storage_type = "ehviewer_dir"

    def storage_signature(self, path):
        return "sig"


async def test_ingest_downloaded_gallery_marks_quality_and_removes_old(
    tmp_path, monkeypatch
):
    new = tmp_path / "new"
    new.mkdir()
    (new / "00000001.jpg").write_bytes(b"x")
    old = tmp_path / "old"
    old.mkdir()
    (old / "00000001.jpg").write_bytes(b"x")

    prev = SimpleNamespace(gid=7, storage_path=str(old), page_count=1)
    session = _FakeSession(prev)
    ingested: list[GalleryMeta] = []
    removed: list[tuple] = []

    class _FakeIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, galleries):
            ingested.extend(galleries)

    async def _fake_remove(result, old_path, old_pages):
        removed.append((result, old_path, old_pages))

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: session
    monkeypatch.setattr(download_worker, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(download_worker, "registry", SimpleNamespace(for_path=lambda p: _FakeScanner()))
    monkeypatch.setattr(download_worker, "remove_superseded_copy", _fake_remove)

    result = SimpleNamespace(
        gid=7, path=str(new), title="T", title_jpn=None, token="tok",
        category="misc", quality="original", pages=1, tags=[],
    )
    try:
        await ingest_downloaded_gallery(result)
    finally:
        app_state.session_factory = orig_factory

    assert ingested and ingested[0].image_quality == "original"
    assert removed and removed[0][0].gid == 7 and removed[0][1] == old


async def test_ingest_downloaded_gallery_skips_removal_for_resample(
    tmp_path, monkeypatch
):
    new = tmp_path / "new"
    new.mkdir()
    (new / "00000001.jpg").write_bytes(b"x")
    session = _FakeSession(None)
    removed = []

    class _FakeIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, galleries):
            pass

    async def _fake_remove(*_args):
        removed.append(True)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: session
    monkeypatch.setattr(download_worker, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(download_worker, "registry", SimpleNamespace(for_path=lambda p: _FakeScanner()))
    monkeypatch.setattr(download_worker, "remove_superseded_copy", _fake_remove)

    result = SimpleNamespace(
        gid=7, path=str(new), title="T", title_jpn=None, token="tok",
        category="misc", quality="resample", pages=1, tags=[],
    )
    try:
        await ingest_downloaded_gallery(result)
    finally:
        app_state.session_factory = orig_factory

    assert not removed


async def test_ingest_downloaded_gallery_prunes_merged_stale_pages(
    tmp_path, monkeypatch
):
    """In-place original upgrade: stale resampled pages with a different
    extension (old .webp) must be pruned before ingest, keeping the new
    original .jpg per page."""
    merged = tmp_path / "merged"
    merged.mkdir()
    new_jpg = merged / "00000001.jpg"
    new_jpg.write_bytes(b"new")
    stale_webp = merged / "00000001.webp"
    stale_webp.write_bytes(b"old")
    # Page 2: same-extension overwrite (no duplicate to prune).
    (merged / "00000002.jpg").write_bytes(b"new")
    (merged / "00000002.jpg").write_bytes(b"new")

    session = _FakeSession(None)
    ingested: list[GalleryMeta] = []

    class _FakeIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, galleries):
            ingested.extend(galleries)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: session
    monkeypatch.setattr(download_worker, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(download_worker, "registry", SimpleNamespace(for_path=lambda p: _FakeScanner()))

    result = SimpleNamespace(
        gid=7, path=str(merged), title="T", title_jpn=None, token="tok",
        category="misc", quality="original", pages=2, tags=[],
        new_files=("00000001.jpg", "00000002.jpg"),
    )
    try:
        await ingest_downloaded_gallery(result)
    finally:
        app_state.session_factory = orig_factory

    assert not stale_webp.exists()
    assert new_jpg.exists()
    assert len(ingested) == 1 and len(ingested[0].pages) == 2
    assert ingested[0].image_quality == "original"


async def test_ingest_downloaded_gallery_keeps_stale_for_resample(
    tmp_path, monkeypatch
):
    """A resample download must not prune same-stem files (no upgrade)."""
    merged = tmp_path / "merged"
    merged.mkdir()
    a = merged / "00000001.jpg"
    a.write_bytes(b"a")
    b = merged / "00000001.webp"
    b.write_bytes(b"b")

    session = _FakeSession(None)
    ingested: list[GalleryMeta] = []

    class _FakeIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, galleries):
            ingested.extend(galleries)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: session
    monkeypatch.setattr(download_worker, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(download_worker, "registry", SimpleNamespace(for_path=lambda p: _FakeScanner()))

    result = SimpleNamespace(
        gid=7, path=str(merged), title="T", title_jpn=None, token="tok",
        category="misc", quality="resample", pages=2, tags=[],
        new_files=("00000001.jpg",),
    )
    try:
        await ingest_downloaded_gallery(result)
    finally:
        app_state.session_factory = orig_factory

    assert a.exists() and b.exists()
    assert len(ingested) == 1 and len(ingested[0].pages) == 2


# --- detail endpoint --------------------------------------------------------


async def test_gallery_detail_exposes_image_quality(monkeypatch):
    from galleryvault.app.routers import galleries as galleries_router

    row = SimpleNamespace(
        id=1, gid=7, token="tok", title="T", title_jpn=None,
        storage_type="ehviewer_dir", category="misc", page_count=1,
        file_size=10, image_quality="original", tags_synced_at=None,
        source_meta={},
    )

    async def _gallery(_identifier):
        return row, []

    async def _tags(_gallery_id):
        return []

    monkeypatch.setattr(galleries_router, "_gallery_lookup", _gallery)
    monkeypatch.setattr(galleries_router, "_gallery_tags_lookup", _tags)
    orig_settings = app_state.settings
    app_state.settings = Settings(
        exhentai_base_url="https://exhentai.org", title_display="japanese"
    )

    try:
        data = await gallery_detail(1)
        assert data["image_quality"] == "original"
    finally:
        app_state.settings = orig_settings


# --- download-original endpoint ---------------------------------------------


class _FakeCreateRepo:
    def __init__(self, task):
        self._task = task
        self.created = None

    def __call__(self, session):
        self._session = session
        return self

    async def create(self, gid, token, title, mode, max_pages, quality, title_jpn=None):
        self.created = (gid, token, mode, max_pages, quality)
        return self._task


class _FakeSettingsSession:
    def __init__(self, repo):
        self._repo = repo

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def begin(self):
        return self


async def test_download_original_page_by_page_enqueues_original(monkeypatch):
    from galleryvault.app.routers import galleries as galleries_router

    row = SimpleNamespace(gid=7, token="tok", title="T")
    repo = _FakeCreateRepo(SimpleNamespace(id=9, gid=7))

    async def _gallery(_identifier):
        return row, []

    class _Client:
        async def fetch_gallery(self, gid, token, max_pages=1, resolve_urls=True):
            assert gid == 7 and max_pages == 1 and resolve_urls is True
            return SimpleNamespace(pages=[SimpleNamespace(origin_url="http://orig")])

    monkeypatch.setattr(galleries_router, "_gallery_lookup", _gallery)
    orig_client = app_state.eh_client
    orig_factory = app_state.session_factory
    app_state.eh_client = _Client()
    app_state.session_factory = _FakeSettingsSession(repo)
    monkeypatch.setattr("galleryvault.app.routers.galleries.DownloadRepository", repo)

    try:
        resp = await download_gallery_original(1, DownloadOriginalRequest(archive=False))
        assert resp == {"id": 9, "gid": 7, "status": "pending"}
        assert repo.created[2] == "gallery" and repo.created[4] == "original"
    finally:
        app_state.eh_client = orig_client
        app_state.session_factory = orig_factory


async def test_download_original_archive_skips_availability_check(monkeypatch):
    from galleryvault.app.routers import galleries as galleries_router

    row = SimpleNamespace(gid=7, token="tok", title="T")
    repo = _FakeCreateRepo(SimpleNamespace(id=9, gid=7))
    fetched = []

    async def _gallery(_identifier):
        return row, []

    class _Client:
        async def fetch_gallery(self, *_args, **_kwargs):
            fetched.append(True)
            return SimpleNamespace(pages=[SimpleNamespace(origin_url=None)])

    monkeypatch.setattr(galleries_router, "_gallery_lookup", _gallery)
    orig_client = app_state.eh_client
    orig_factory = app_state.session_factory
    app_state.eh_client = _Client()
    app_state.session_factory = _FakeSettingsSession(repo)
    monkeypatch.setattr("galleryvault.app.routers.galleries.DownloadRepository", repo)

    try:
        resp = await download_gallery_original(1, DownloadOriginalRequest(archive=True))
        assert resp == {"id": 9, "gid": 7, "status": "pending"}
        assert not fetched
        assert repo.created[2] == "gallery_archive" and repo.created[4] == "original"
    finally:
        app_state.eh_client = orig_client
        app_state.session_factory = orig_factory


async def test_download_original_rejects_missing_original(monkeypatch):
    from galleryvault.app.routers import galleries as galleries_router

    row = SimpleNamespace(gid=7, token="tok", title="T")
    repo = _FakeCreateRepo(SimpleNamespace(id=9, gid=7))

    async def _gallery(_identifier):
        return row, []

    class _Client:
        async def fetch_gallery(self, *_args, **_kwargs):
            return SimpleNamespace(pages=[SimpleNamespace(origin_url=None)])

    monkeypatch.setattr(galleries_router, "_gallery_lookup", _gallery)
    orig_client = app_state.eh_client
    orig_factory = app_state.session_factory
    app_state.eh_client = _Client()
    app_state.session_factory = _FakeSettingsSession(repo)
    monkeypatch.setattr("galleryvault.app.routers.galleries.DownloadRepository", repo)

    try:
        with pytest.raises(Exception) as exc_info:
            await download_gallery_original(1, DownloadOriginalRequest(archive=False))
        assert "No original images available" in str(exc_info.value)
    finally:
        app_state.eh_client = orig_client
        app_state.session_factory = orig_factory


async def test_download_original_rejects_local_only_gallery(monkeypatch):
    from galleryvault.app.routers import galleries as galleries_router

    row = SimpleNamespace(gid=None, token=None, title="T")

    async def _gallery(_identifier):
        return row, []

    monkeypatch.setattr(galleries_router, "_gallery_lookup", _gallery)

    with pytest.raises(Exception) as exc_info:
        await download_gallery_original(1, DownloadOriginalRequest(archive=False))
    assert "no ExHentai gid/token" in str(exc_info.value)


async def test_download_original_conflicts_with_active_task(monkeypatch):
    from galleryvault.app.routers import galleries as galleries_router

    row = SimpleNamespace(gid=7, token="tok", title="T")
    repo = _FakeCreateRepo(None)

    async def _gallery(_identifier):
        return row, []

    class _Client:
        async def fetch_gallery(self, *_args, **_kwargs):
            return SimpleNamespace(pages=[SimpleNamespace(origin_url="http://orig")])

    monkeypatch.setattr(galleries_router, "_gallery_lookup", _gallery)
    orig_client = app_state.eh_client
    orig_factory = app_state.session_factory
    app_state.eh_client = _Client()
    app_state.session_factory = _FakeSettingsSession(repo)
    monkeypatch.setattr("galleryvault.app.routers.galleries.DownloadRepository", repo)

    try:
        with pytest.raises(Exception) as exc_info:
            await download_gallery_original(1, DownloadOriginalRequest(archive=False))
        assert "already exists" in str(exc_info.value)
    finally:
        app_state.eh_client = orig_client
        app_state.session_factory = orig_factory


async def test_ingest_downloaded_gallery_handles_tuple_tags(tmp_path, monkeypatch):
    """Ensure tuple tags (from Downloader.execute) ingest correctly without AttributeError."""
    from galleryvault.services.downloader import DownloadResult

    new = tmp_path / "4161431-gallery"
    new.mkdir()
    (new / "00000001.jpg").write_bytes(b"x")
    (new / "00000002.jpg").write_bytes(b"y")

    session = _FakeSession(None)
    ingested: list[GalleryMeta] = []

    class _FakeIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, galleries):
            ingested.extend(galleries)

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: session
    monkeypatch.setattr(download_worker, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(download_worker, "registry", SimpleNamespace(for_path=lambda p: _FakeScanner()))

    result = DownloadResult(
        gid=4161431,
        path=new,
        pages=2,
        category="misc",
        title="Sample Gallery",
        title_jpn="サンプル",
        token="tok123",
        tags=(("artist", "test_artist"), ("female", "sole female")),
        quality="resample",
        new_files=(),
    )
    try:
        await ingest_downloaded_gallery(result)
    finally:
        app_state.session_factory = orig_factory

    assert len(ingested) == 1
    assert ingested[0].gid == 4161431
    assert ingested[0].tags == [
        {"namespace": "artist", "name": "test_artist"},
        {"namespace": "female", "name": "sole female"},
    ]
    assert ingested[0].file_count == 2


# --- favorites download-selected endpoint ----------------------------------


async def test_favorites_download_selected_original_upgrades_resample(monkeypatch):
    from galleryvault.app.routers import favorites as favorites_router
    from galleryvault.app.schemas import DownloadSelectedRequest

    detail = {
        101: {
            "gid": 101,
            "token": "tok101",
            "title": "cloud_only",
            "gallery_id": None,
            "image_quality": None,
        },
        102: {
            "gid": 102,
            "token": "tok102",
            "title": "local_orig",
            "gallery_id": 12,
            "image_quality": "original",
        },
        103: {
            "gid": 103,
            "token": "tok103",
            "title": "local_resample",
            "gallery_id": 13,
            "image_quality": "resample",
        },
        104: {
            "gid": 104,
            "token": "tok104",
            "title": "local_unknown",
            "gallery_id": 14,
            "image_quality": None,
        },
        105: {
            "gid": 105,
            "token": "tok105",
            "title": "local_empty",
            "gallery_id": 15,
            "image_quality": "",
        },
        106: {
            "gid": 106,
            "token": "",
            "title": "no_token",
            "gallery_id": None,
            "image_quality": None,
        },
    }

    class _FakeFavRepo:
        def __init__(self, _session):
            pass

        async def favorite_items_detail_by_gids(self, gids):
            return {g: detail[g] for g in gids if g in detail}

    async def _fake_session():
        yield object()

    enqueued = []

    class _FakeQueue:
        async def enqueue(self, item, mode="favorite", quality=None):
            enqueued.append((item.gid, item.token, item.title, mode, quality))
            return True

    monkeypatch.setattr(favorites_router, "FavoritesRepository", _FakeFavRepo)
    monkeypatch.setattr(favorites_router, "get_session", _fake_session)
    monkeypatch.setattr(favorites_router, "FavoriteDownloadQueue", _FakeQueue)

    # 1. quality="original", archive=False
    req = DownloadSelectedRequest(gids=[101, 102, 103, 104, 105, 106], quality="original")
    resp = await favorites_router.favorites_download_selected(req)
    assert resp == {"queued": 4, "skipped": 2}

    # Verify enqueued modes and qualities
    assert enqueued == [
        (101, "tok101", "cloud_only", "favorite", "original"),
        (103, "tok103", "local_resample", "gallery", "original"),
        (104, "tok104", "local_unknown", "gallery", "original"),
        (105, "tok105", "local_empty", "gallery", "original"),
    ]


async def test_favorites_download_selected_archive_original_upgrades_resample(monkeypatch):
    from galleryvault.app.routers import favorites as favorites_router
    from galleryvault.app.schemas import DownloadSelectedRequest

    detail = {
        101: {
            "gid": 101,
            "token": "tok101",
            "title": "cloud_only",
            "gallery_id": None,
            "image_quality": None,
        },
        102: {
            "gid": 102,
            "token": "tok102",
            "title": "local_orig",
            "gallery_id": 12,
            "image_quality": "original",
        },
        103: {
            "gid": 103,
            "token": "tok103",
            "title": "local_resample",
            "gallery_id": 13,
            "image_quality": "resample",
        },
        104: {
            "gid": 104,
            "token": "tok104",
            "title": "local_unknown",
            "gallery_id": 14,
            "image_quality": None,
        },
        105: {
            "gid": 105,
            "token": "tok105",
            "title": "local_empty",
            "gallery_id": 15,
            "image_quality": "",
        },
        106: {
            "gid": 106,
            "token": "",
            "title": "no_token",
            "gallery_id": None,
            "image_quality": None,
        },
    }

    class _FakeFavRepo:
        def __init__(self, _session):
            pass

        async def favorite_items_detail_by_gids(self, gids):
            return {g: detail[g] for g in gids if g in detail}

    async def _fake_session():
        yield object()

    enqueued = []

    class _FakeQueue:
        async def enqueue(self, item, mode="favorite", quality=None):
            enqueued.append((item.gid, item.token, item.title, mode, quality))
            return True

    monkeypatch.setattr(favorites_router, "FavoritesRepository", _FakeFavRepo)
    monkeypatch.setattr(favorites_router, "get_session", _fake_session)
    monkeypatch.setattr(favorites_router, "FavoriteDownloadQueue", _FakeQueue)

    req = DownloadSelectedRequest(
        gids=[101, 102, 103, 104, 105, 106],
        archive=True,
        quality="original",
    )
    resp = await favorites_router.favorites_download_selected(req)
    assert resp == {"queued": 4, "skipped": 2}

    # 101: cloud-only -> favorite_archive, original
    # 102: local original -> skipped
    # 103, 104, 105: local non-original -> gallery_archive, original
    # 106: missing token -> skipped
    assert enqueued == [
        (101, "tok101", "cloud_only", "favorite_archive", "original"),
        (103, "tok103", "local_resample", "gallery_archive", "original"),
        (104, "tok104", "local_unknown", "gallery_archive", "original"),
        (105, "tok105", "local_empty", "gallery_archive", "original"),
    ]


async def test_favorites_download_selected_non_original_skips_all_local(monkeypatch):
    from galleryvault.app.routers import favorites as favorites_router
    from galleryvault.app.schemas import DownloadSelectedRequest

    detail = {
        101: {
            "gid": 101,
            "token": "tok101",
            "title": "cloud_only",
            "gallery_id": None,
            "image_quality": None,
        },
        102: {
            "gid": 102,
            "token": "tok102",
            "title": "local_resample",
            "gallery_id": 13,
            "image_quality": "resample",
        },
        103: {
            "gid": 103,
            "token": "tok103",
            "title": "local_orig",
            "gallery_id": 12,
            "image_quality": "original",
        },
    }

    class _FakeFavRepo:
        def __init__(self, _session):
            pass

        async def favorite_items_detail_by_gids(self, gids):
            return {g: detail[g] for g in gids if g in detail}

    async def _fake_session():
        yield object()

    enqueued = []

    class _FakeQueue:
        async def enqueue(self, item, mode="favorite", quality=None):
            enqueued.append((item.gid, item.token, item.title, mode, quality))
            return True

    monkeypatch.setattr(favorites_router, "FavoritesRepository", _FakeFavRepo)
    monkeypatch.setattr(favorites_router, "get_session", _fake_session)
    monkeypatch.setattr(favorites_router, "FavoriteDownloadQueue", _FakeQueue)

    # 1. regular download (quality=None, archive=False): local skipped, quality defaults to settings
    enqueued.clear()
    resp_regular = await favorites_router.favorites_download_selected(
        DownloadSelectedRequest(gids=[101, 102, 103])
    )
    assert resp_regular == {"queued": 1, "skipped": 2}
    assert enqueued == [(101, "tok101", "cloud_only", "favorite", "resample")]

    # 2. regular download with resample: local skipped
    enqueued.clear()
    resp_resample = await favorites_router.favorites_download_selected(
        DownloadSelectedRequest(gids=[101, 102, 103], quality="resample")
    )
    assert resp_resample == {"queued": 1, "skipped": 2}
    assert enqueued == [(101, "tok101", "cloud_only", "favorite", "resample")]

    # 3. archive download with resample: local skipped (clause 4)
    enqueued.clear()
    resp_archive_resample = await favorites_router.favorites_download_selected(
        DownloadSelectedRequest(gids=[101, 102, 103], archive=True, quality="resample")
    )
    assert resp_archive_resample == {"queued": 1, "skipped": 2}
    assert enqueued == [(101, "tok101", "cloud_only", "favorite_archive", "resample")]

    # 4. archive download with default/None quality: local skipped
    enqueued.clear()
    resp_archive_default = await favorites_router.favorites_download_selected(
        DownloadSelectedRequest(gids=[101, 102, 103], archive=True)
    )
    assert resp_archive_default == {"queued": 1, "skipped": 2}
    assert enqueued == [(101, "tok101", "cloud_only", "favorite_archive", "resample")]

    # 5. regular download when settings.download_quality="original": local still skipped, unarchived enqueued as "original"
    orig_settings = app_state.settings
    try:
        app_state.settings = Settings(download_quality="original")
        enqueued.clear()
        resp_setting_original = await favorites_router.favorites_download_selected(
            DownloadSelectedRequest(gids=[101, 102, 103])
        )
        assert resp_setting_original == {"queued": 1, "skipped": 2}
        assert enqueued == [(101, "tok101", "cloud_only", "favorite", "original")]
    finally:
        app_state.settings = orig_settings


async def test_favorite_items_detail_by_gids_includes_image_quality():
    from galleryvault.db.repositories.favorites import FavoritesRepository

    item1 = SimpleNamespace(
        gid=1, favcat=0, token="t1", title="T1", url="u1", file_size=100, first_seen_at=None
    )
    gal1 = SimpleNamespace(
        id=10,
        gid=1,
        token="t1",
        title="G1",
        category="misc",
        page_count=5,
        file_size=200,
        posted_at=None,
        image_quality="resample",
    )
    item2 = SimpleNamespace(
        gid=2, favcat=1, token="t2", title="T2", url="u2", file_size=150, first_seen_at=None
    )

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

        def __iter__(self):
            return iter(self._rows)

    calls = 0

    class _FakeSession:
        async def execute(self, _statement):
            nonlocal calls
            calls += 1
            if calls == 1:
                return _FakeResult([(item1, gal1), (item2, None)])
            return _FakeResult([])

    repo = FavoritesRepository(_FakeSession())
    res = await repo.favorite_items_detail_by_gids([1, 2])
    assert res[1]["image_quality"] == "resample"
    assert res[1]["gallery_id"] == 10
    assert res[2]["image_quality"] is None
    assert res[2]["gallery_id"] is None
