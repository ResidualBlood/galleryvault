"""T2.4: redownload/supersede must not cross the download-root boundary.

The original-quality upgrade used to remove the previous copy without passing
the configured scan roots. A gallery stored under a (possibly read-only)
library root was therefore deleted silently; a copy outside every root had its
rmtree error swallowed. The fix keeps library copies, registers them as a
duplicate group for the cleanup page, and makes the API require an explicit
``allow_copy=true`` before writing a second copy outside ``download_root``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from galleryvault.app.routers import galleries as galleries_router
from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.db.models import DuplicateRecord
from galleryvault.services import download_worker, updates_worker
from galleryvault.services.download_worker import ingest_downloaded_gallery


class _FakeSession:
    """Minimal async session double for the ingest path."""

    def __init__(self, prev=None, duplicate=None):
        self._prev = prev
        self._duplicate = duplicate
        self.added: list[object] = []

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def begin(self):
        return self

    def in_transaction(self):
        return False

    async def scalar(self, _stmt):
        return self._prev

    async def get(self, _model, _pk):
        return self._duplicate

    def add(self, obj):
        self.added.append(obj)


class _FakeScanner:
    storage_type = "ehviewer_dir"

    def storage_signature(self, _path):
        return "sig"


class _FakeIngest:
    def __init__(self, _session):
        pass

    async def ingest(self, _galleries):
        return None


class _FakeDownloadRepo:
    def __init__(self):
        self.created = None

    async def create(self, *args, **kwargs):
        self.created = (args, kwargs)
        return SimpleNamespace(id=9, gid=7)


class _FakeSettingsSession(_FakeSession):
    pass


def _settings(tmp_path, *, library: str, download: str) -> Settings:
    return Settings(
        library_roots=[library],
        download_root=download,
        auto_archive_downloads=False,
    )


def _patch_ingest(monkeypatch, tmp_path, session, settings):
    async def _noop_finalize(*_args, **_kwargs):
        return None

    monkeypatch.setattr(updates_worker, "finalize_updates_for_new_gid", _noop_finalize)
    monkeypatch.setattr(download_worker, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(
        download_worker,
        "registry",
        SimpleNamespace(for_path=lambda _path: _FakeScanner()),
    )
    monkeypatch.setattr(app_state, "settings", settings)
    monkeypatch.setattr(app_state, "session_factory", lambda: session)
    monkeypatch.setattr(app_state, "worker_session_factory", None)
    monkeypatch.setattr(app_state, "worker_engine", None)


def _make_copy(root, name: str) -> None:
    gallery = root / name
    gallery.mkdir(parents=True)
    (gallery / "00000001.jpg").write_bytes(b"x")


def _result(new_path):
    return SimpleNamespace(
        gid=7,
        path=str(new_path),
        title="T",
        title_jpn=None,
        token="tok",
        category="misc",
        quality="original",
        pages=1,
        tags=[],
        new_files=(),
    )


async def test_supersede_never_deletes_under_library_root(tmp_path, monkeypatch):
    library_root = tmp_path / "library"
    download_root = tmp_path / "downloads"
    old = library_root / "7-gallery"
    new = download_root / "7-gallery"
    _make_copy(library_root, old.name)
    _make_copy(download_root, new.name)

    prev = SimpleNamespace(gid=7, storage_path=str(old), page_count=1)
    session = _FakeSession(prev=prev, duplicate=None)
    _patch_ingest(
        monkeypatch,
        tmp_path,
        session,
        _settings(tmp_path, library=str(library_root), download=str(download_root)),
    )

    await ingest_downloaded_gallery(_result(new))

    assert old.exists(), "library-root copy must never be deleted by a redownload"
    assert session.added, "the kept copy must be registered as a duplicate"
    record = session.added[0]
    assert isinstance(record, DuplicateRecord)
    assert record.gid == 7
    assert record.status == "open"
    paths = {copy["path"] for copy in record.copies}
    assert paths == {str(old), str(new)}
    assert record.winner_path == str(new)


async def test_supersede_deletes_download_root_copy_with_scan_roots(tmp_path, monkeypatch):
    library_root = tmp_path / "library"
    download_root = tmp_path / "downloads"
    old = download_root / "7-gallery"
    new = download_root / "7-new"
    _make_copy(download_root, old.name)
    _make_copy(download_root, new.name)

    prev = SimpleNamespace(gid=7, storage_path=str(old), page_count=1)
    session = _FakeSession(prev=prev)
    calls: list[dict] = []

    async def _spy(_result, old_path, old_pages, **kwargs):
        calls.append({"path": old_path, "pages": old_pages, "kwargs": kwargs})

    _patch_ingest(
        monkeypatch,
        tmp_path,
        session,
        _settings(tmp_path, library=str(library_root), download=str(download_root)),
    )
    monkeypatch.setattr(download_worker, "remove_superseded_copy", _spy)
    monkeypatch.setattr(
        "galleryvault.app.dependencies.get_scan_roots",
        lambda: [str(download_root)],
    )

    await ingest_downloaded_gallery(_result(new))

    assert calls and calls[0]["path"] == old
    assert calls[0]["kwargs"].get("scan_roots") == [str(download_root)]
    assert not session.added


async def test_redownload_library_root_requires_allow_copy(tmp_path, monkeypatch):
    library_root = tmp_path / "library"
    download_root = tmp_path / "downloads"
    storage_path = library_root / "7-gallery"
    storage_path.mkdir(parents=True)

    row = SimpleNamespace(
        gid=7,
        token="tok",
        title="T",
        title_jpn=None,
        image_quality=None,
        storage_path=str(storage_path),
    )
    repo = _FakeDownloadRepo()

    async def _gallery(_identifier, session=None):
        return row, []

    monkeypatch.setattr(galleries_router, "_gallery_lookup", _gallery)
    monkeypatch.setattr(galleries_router, "DownloadRepository", lambda _session: repo)
    monkeypatch.setattr(
        app_state,
        "settings",
        _settings(tmp_path, library=str(library_root), download=str(download_root)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await galleries_router.redownload_gallery(1, session=_FakeSettingsSession())

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "requires_copy"
    assert repo.created is None


async def test_redownload_library_root_allow_copy_enqueues(tmp_path, monkeypatch):
    library_root = tmp_path / "library"
    download_root = tmp_path / "downloads"
    storage_path = library_root / "7-gallery"
    storage_path.mkdir(parents=True)

    row = SimpleNamespace(
        gid=7,
        token="tok",
        title="T",
        title_jpn=None,
        image_quality=None,
        storage_path=str(storage_path),
    )
    repo = _FakeDownloadRepo()

    async def _gallery(_identifier, session=None):
        return row, []

    monkeypatch.setattr(galleries_router, "_gallery_lookup", _gallery)
    monkeypatch.setattr(galleries_router, "DownloadRepository", lambda _session: repo)
    monkeypatch.setattr(
        app_state,
        "settings",
        _settings(tmp_path, library=str(library_root), download=str(download_root)),
    )

    resp = await galleries_router.redownload_gallery(
        1, allow_copy=True, session=_FakeSettingsSession()
    )

    assert resp == {"status": "pending", "task_id": 9, "gid": 7}
    assert repo.created is not None


async def test_redownload_download_root_needs_no_confirmation(tmp_path, monkeypatch):
    library_root = tmp_path / "library"
    download_root = tmp_path / "downloads"
    storage_path = download_root / "7-gallery"
    storage_path.mkdir(parents=True)

    row = SimpleNamespace(
        gid=7,
        token="tok",
        title="T",
        title_jpn=None,
        image_quality=None,
        storage_path=str(storage_path),
    )
    repo = _FakeDownloadRepo()

    async def _gallery(_identifier, session=None):
        return row, []

    monkeypatch.setattr(galleries_router, "_gallery_lookup", _gallery)
    monkeypatch.setattr(galleries_router, "DownloadRepository", lambda _session: repo)
    monkeypatch.setattr(
        app_state,
        "settings",
        _settings(tmp_path, library=str(library_root), download=str(download_root)),
    )

    resp = await galleries_router.redownload_gallery(1, session=_FakeSettingsSession())

    assert resp["task_id"] == 9
    assert repo.created is not None
