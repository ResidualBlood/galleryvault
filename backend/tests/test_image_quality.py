"""Image-quality tracking: inference, superseded-copy cleanup, endpoints.

Covers the original-upgrade feature: the ``image_quality`` inference from
local size vs the ExHentai original size, the automatic removal of the old
resampled copy after an original download, and the gallery-detail download
endpoint (page-by-page and archive forms).
"""

from types import SimpleNamespace

import pytest

from galleryvault.app import main
from galleryvault.app.routers.galleries import (
    DownloadOriginalRequest,
    download_gallery_original,
    gallery_detail,
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
    assert main._infer_image_quality(1000, 1100) == "original"
    assert main._infer_image_quality(935, 1000) == "original"  # ratio 0.935


def test_infer_image_quality_resample_when_smaller():
    assert main._infer_image_quality(500, 1000) == "resample"
    assert main._infer_image_quality(840, 1000) == "resample"  # ratio 0.84


def test_infer_image_quality_cbz_uses_looser_threshold():
    assert main._infer_image_quality(820, 1000, "cbz") == "original"  # 0.82
    assert main._infer_image_quality(790, 1000, "cbz") == "resample"
    # A non-cbz copy at the same ratio is still resample.
    assert main._infer_image_quality(820, 1000, "ehviewer_dir") == "resample"


def test_infer_image_quality_returns_none_without_data():
    assert main._infer_image_quality(None, 1000) is None
    assert main._infer_image_quality(1000, None) is None
    assert main._infer_image_quality(0, 1000) is None


# --- superseded-copy removal ------------------------------------------------


def _result(path, pages=2, quality="original"):
    return SimpleNamespace(gid=7, path=path, pages=pages, quality=quality)


async def test_remove_superseded_copy_deletes_matching_old_dir(tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    (old / "00000001.jpg").write_bytes(b"x")
    new = tmp_path / "new"
    new.mkdir()
    await main._remove_superseded_copy(_result(str(new), pages=2), old, 2)
    assert not old.exists()


async def test_remove_superseded_copy_keeps_on_page_mismatch(tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    (old / "00000001.jpg").write_bytes(b"x")
    new = tmp_path / "new"
    new.mkdir()
    await main._remove_superseded_copy(_result(str(new), pages=3), old, 2)
    assert old.exists()


async def test_remove_superseded_copy_keeps_when_same_path(tmp_path):
    new = tmp_path / "new"
    new.mkdir()
    (new / "00000001.jpg").write_bytes(b"x")
    await main._remove_superseded_copy(_result(str(new), pages=2), new, 2)
    assert new.exists()


async def test_remove_superseded_copy_unlinks_single_file(tmp_path):
    old = tmp_path / "old.cbz"
    old.write_bytes(b"archive")
    new = tmp_path / "new"
    new.mkdir()
    await main._remove_superseded_copy(_result(str(new), pages=2), old, 2)
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
    await main._remove_superseded_copy(_result(str(new), pages=2), old, 2)
    assert old.exists()


# --- ingest marking ---------------------------------------------------------


class _FakeSession:
    """Minimal settings-session double for _ingest_downloaded_gallery."""

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
    ingested: list[main.GalleryMeta] = []
    removed: list[tuple] = []

    class _FakeIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, galleries):
            ingested.extend(galleries)

    async def _fake_remove(result, old_path, old_pages):
        removed.append((result, old_path, old_pages))

    monkeypatch.setattr(main, "_settings_session", lambda: session)
    monkeypatch.setattr(main, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(main, "registry", SimpleNamespace(for_path=lambda p: _FakeScanner()))
    monkeypatch.setattr(main, "_remove_superseded_copy", _fake_remove)
    monkeypatch.setattr(main, "_settings", lambda: SimpleNamespace(generate_thumbnails=False))

    result = SimpleNamespace(
        gid=7, path=str(new), title="T", title_jpn=None, token="tok",
        category="misc", quality="original", pages=1, tags=[],
    )
    await main._ingest_downloaded_gallery(result)

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

    monkeypatch.setattr(main, "_settings_session", lambda: session)
    monkeypatch.setattr(main, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(main, "registry", SimpleNamespace(for_path=lambda p: _FakeScanner()))
    monkeypatch.setattr(main, "_remove_superseded_copy", _fake_remove)
    monkeypatch.setattr(main, "_settings", lambda: SimpleNamespace(generate_thumbnails=False))

    result = SimpleNamespace(
        gid=7, path=str(new), title="T", title_jpn=None, token="tok",
        category="misc", quality="resample", pages=1, tags=[],
    )
    await main._ingest_downloaded_gallery(result)
    assert not removed


# --- detail endpoint --------------------------------------------------------


async def test_gallery_detail_exposes_image_quality(monkeypatch):
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

    monkeypatch.setattr(main, "_gallery", _gallery)
    monkeypatch.setattr(main, "_gallery_tags", _tags)
    monkeypatch.setattr(main, "_settings", lambda: SimpleNamespace(
        exhentai_base_url="https://exhentai.org", title_display="japanese"
    ))

    data = await gallery_detail(1)
    assert data["image_quality"] == "original"


# --- download-original endpoint ---------------------------------------------


class _FakeCreateRepo:
    def __init__(self, task):
        self._task = task
        self.created = None

    def __call__(self, session):
        self._session = session
        return self

    async def create(self, gid, token, title, mode, max_pages, quality):
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
    row = SimpleNamespace(gid=7, token="tok", title="T")
    repo = _FakeCreateRepo(SimpleNamespace(id=9, gid=7))

    async def _gallery(_identifier):
        return row, []

    class _Client:
        async def fetch_gallery(self, gid, token, max_pages=1, resolve_urls=True):
            assert gid == 7 and max_pages == 1 and resolve_urls is True
            return SimpleNamespace(pages=[SimpleNamespace(origin_url="http://orig")])

    monkeypatch.setattr(main, "_gallery", _gallery)
    monkeypatch.setattr(main, "app", SimpleNamespace(state=SimpleNamespace(eh_client=_Client())))
    monkeypatch.setattr(main, "_settings_session", _FakeSettingsSession(repo))
    monkeypatch.setattr("galleryvault.app.routers.galleries.DownloadRepository", repo)

    resp = await download_gallery_original(1, DownloadOriginalRequest(archive=False))
    assert resp == {"id": 9, "gid": 7, "status": "pending"}
    assert repo.created[2] == "gallery" and repo.created[4] == "original"


async def test_download_original_archive_skips_availability_check(monkeypatch):
    row = SimpleNamespace(gid=7, token="tok", title="T")
    repo = _FakeCreateRepo(SimpleNamespace(id=9, gid=7))
    fetched = []

    async def _gallery(_identifier):
        return row, []

    class _Client:
        async def fetch_gallery(self, *_args, **_kwargs):
            fetched.append(True)
            return SimpleNamespace(pages=[SimpleNamespace(origin_url=None)])

    monkeypatch.setattr(main, "_gallery", _gallery)
    monkeypatch.setattr(main, "app", SimpleNamespace(state=SimpleNamespace(eh_client=_Client())))
    monkeypatch.setattr(main, "_settings_session", _FakeSettingsSession(repo))
    monkeypatch.setattr("galleryvault.app.routers.galleries.DownloadRepository", repo)

    resp = await download_gallery_original(1, DownloadOriginalRequest(archive=True))
    assert resp == {"id": 9, "gid": 7, "status": "pending"}
    assert not fetched
    assert repo.created[2] == "gallery_archive" and repo.created[4] == "original"


async def test_download_original_rejects_missing_original(monkeypatch):
    row = SimpleNamespace(gid=7, token="tok", title="T")
    repo = _FakeCreateRepo(SimpleNamespace(id=9, gid=7))

    async def _gallery(_identifier):
        return row, []

    class _Client:
        async def fetch_gallery(self, *_args, **_kwargs):
            return SimpleNamespace(pages=[SimpleNamespace(origin_url=None)])

    monkeypatch.setattr(main, "_gallery", _gallery)
    monkeypatch.setattr(main, "app", SimpleNamespace(state=SimpleNamespace(eh_client=_Client())))
    monkeypatch.setattr(main, "_settings_session", _FakeSettingsSession(repo))
    monkeypatch.setattr("galleryvault.app.routers.galleries.DownloadRepository", repo)

    with pytest.raises(Exception) as exc_info:
        await download_gallery_original(1, DownloadOriginalRequest(archive=False))
    assert "No original images available" in str(exc_info.value)


async def test_download_original_rejects_local_only_gallery(monkeypatch):
    row = SimpleNamespace(gid=None, token=None, title="T")

    async def _gallery(_identifier):
        return row, []

    monkeypatch.setattr(main, "_gallery", _gallery)

    with pytest.raises(Exception) as exc_info:
        await download_gallery_original(1, DownloadOriginalRequest(archive=False))
    assert "no ExHentai gid/token" in str(exc_info.value)


async def test_download_original_conflicts_with_active_task(monkeypatch):
    row = SimpleNamespace(gid=7, token="tok", title="T")
    repo = _FakeCreateRepo(None)

    async def _gallery(_identifier):
        return row, []

    class _Client:
        async def fetch_gallery(self, *_args, **_kwargs):
            return SimpleNamespace(pages=[SimpleNamespace(origin_url="http://orig")])

    monkeypatch.setattr(main, "_gallery", _gallery)
    monkeypatch.setattr(main, "app", SimpleNamespace(state=SimpleNamespace(eh_client=_Client())))
    monkeypatch.setattr(main, "_settings_session", _FakeSettingsSession(repo))
    monkeypatch.setattr("galleryvault.app.routers.galleries.DownloadRepository", repo)

    with pytest.raises(Exception) as exc_info:
        await download_gallery_original(1, DownloadOriginalRequest(archive=False))
    assert "already exists" in str(exc_info.value)
