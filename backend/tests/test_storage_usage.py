"""Tests for storage usage snapshotting, calibration, and incremental delta tracking."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from galleryvault.app.main import app
from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.services.storage_usage import (
    StorageUsageTracker,
    measure_dir_bytes,
    safe_stat_size,
    storage_tracker,
)


@pytest.mark.asyncio
async def test_safe_stat_size_and_measure(tmp_path: Path) -> None:
    d = tmp_path / "sub"
    d.mkdir()
    f1 = d / "f1.bin"
    f1.write_bytes(b"12345")
    f2 = d / "f2.bin"
    f2.write_bytes(b"67890abcde")  # 10 bytes

    assert safe_stat_size(f1) == 5
    assert safe_stat_size(d) == 15
    assert safe_stat_size(tmp_path / "nonexistent") == 0

    measured = await measure_dir_bytes(d)
    assert measured >= 15


@pytest.mark.asyncio
async def test_storage_tracker_deltas_and_calibrate(tmp_path: Path) -> None:
    tracker = StorageUsageTracker()
    dl_root = tmp_path / "downloads"
    dl_root.mkdir()
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    # Initial state
    assert tracker.downloads.computing is True
    assert tracker.downloads.bytes is None

    # Expected baseline
    dl_base = await measure_dir_bytes(dl_root)
    cache_base = await measure_dir_bytes(cache_root)

    # Calibrate empty roots
    await tracker.calibrate(dl_root, cache_root)
    assert tracker.downloads.computing is False
    assert tracker.downloads.bytes == dl_base
    assert tracker.cache.bytes == cache_base
    assert tracker.downloads.computed_at is not None

    # Deltas after calibration
    tracker.record_download_delta(200)
    tracker.record_download_delta(-50)
    assert tracker.downloads.bytes == dl_base + 150

    tracker.record_cache_delta(30)
    assert tracker.cache.bytes == cache_base + 30


def test_system_storage_api_fast_and_no_walk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_state.settings = Settings(
        auth_required=False,
        download_root=str(tmp_path / "dl"),
        thumbnail_cache_dir=str(tmp_path / "cache" / "thumbs"),
        library_roots=[str(tmp_path / "lib")],
    )

    # Set known storage_tracker state
    storage_tracker.downloads.bytes = 1024
    storage_tracker.downloads.computing = False
    storage_tracker.cache.bytes = 512
    storage_tracker.cache.computing = False

    # Ensure os.walk is never called inside GET /api/system/storage
    walk_called = []
    original_walk = __import__("os").walk

    def forbidden_walk(*args, **kwargs):
        walk_called.append(args)
        return original_walk(*args, **kwargs)

    monkeypatch.setattr("os.walk", forbidden_walk)

    client = TestClient(app)
    resp = client.get("/api/system/storage")
    assert resp.status_code == 200
    data = resp.json()

    assert "library" in data
    assert "downloads" in data
    assert "cache" in data
    assert "largest" in data

    assert data["downloads"]["bytes"] == 1024
    assert data["downloads"]["computing"] is False
    assert data["cache"]["bytes"] == 512
    assert data["cache"]["computing"] is False

    # Verify os.walk was NOT called
    assert len(walk_called) == 0


def test_system_storage_api_no_snapshot(tmp_path: Path) -> None:
    app_state.settings = Settings(
        auth_required=False,
        download_root=str(tmp_path / "dl"),
        thumbnail_cache_dir=str(tmp_path / "cache" / "thumbs"),
        library_roots=[str(tmp_path / "lib")],
    )
    storage_tracker.downloads.bytes = None
    storage_tracker.downloads.computing = True

    client = TestClient(app)
    resp = client.get("/api/system/storage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["downloads"]["bytes"] is None
    assert data["downloads"]["computing"] is True


@pytest.mark.asyncio
async def test_deletion_decrements_download_storage(tmp_path: Path) -> None:
    from galleryvault.services.deletion import delete_local_copy

    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()
    lib_dir = tmp_path / "library"
    lib_dir.mkdir()

    class DummyDownloader:
        root = dl_dir

    app_state.downloader = DummyDownloader()

    storage_tracker.downloads.bytes = 1000

    # Delete file in download_root
    target_dl = dl_dir / "item1"
    target_dl.mkdir()
    (target_dl / "page1.jpg").write_bytes(b"x" * 200)

    res = delete_local_copy(target_dl, roots=[str(dl_dir), str(lib_dir)])
    assert res is True
    assert storage_tracker.downloads.bytes == 800

    # Delete file in library (not download_root) -> should NOT decrement download_tracker
    target_lib = lib_dir / "item2"
    target_lib.mkdir()
    (target_lib / "page1.jpg").write_bytes(b"y" * 150)

    res = delete_local_copy(target_lib, roots=[str(dl_dir), str(lib_dir)])
    assert res is True
    assert storage_tracker.downloads.bytes == 800  # Unchanged


def test_thumbnail_and_favorites_increments_cache(tmp_path: Path) -> None:
    from PIL import Image

    from galleryvault.services.favorites_worker import _write_cover_file
    from galleryvault.services.thumbnails import ThumbnailService

    storage_tracker.cache.bytes = 500

    # 1. Favorites cover write
    cover_file = tmp_path / "remote-covers" / "123.img"
    cover_raw = b"cover_bytes_1234567890"  # 22 bytes
    _write_cover_file(cover_file, cover_raw)
    assert storage_tracker.cache.bytes == 522

    # 2. ThumbnailService write
    thumb_dir = tmp_path / "thumbs"
    svc = ThumbnailService(thumb_dir)
    img = Image.new("RGB", (100, 100), color="red")
    import io

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_img = buf.getvalue()

    svc.get_or_create(gallery_id=999, page_index=0, page_bytes=raw_img)
    assert storage_tracker.cache.bytes > 522


@pytest.mark.asyncio
async def test_purge_archived_sources_internal(tmp_path: Path) -> None:
    from typing import Any

    from galleryvault.services.cold_archive import purge_archived_sources_internal

    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()
    lib_dir = tmp_path / "library"
    lib_dir.mkdir()
    cold_dir = tmp_path / "cold"
    cold_dir.mkdir()

    app_state.settings = Settings(
        auth_required=False,
        download_root=str(dl_dir),
        library_roots=[str(lib_dir)],
        cold_storage_root=str(cold_dir),
        archive_roots=[str(cold_dir)],
    )

    storage_tracker.downloads.bytes = 5000

    # 1. 模拟已归档画廊在 dl_dir 的残留文件夹：gid 1001
    g1_dir = dl_dir / "1001-gallery-one"
    g1_dir.mkdir()
    (g1_dir / "0001.jpg").write_bytes(b"x" * 1000)

    # 2. 模拟已归档画廊在 lib_dir 包含 .ehviewer 的残留文件夹：gid 1002
    g2_dir = lib_dir / "gallery-two"
    g2_dir.mkdir()
    (g2_dir / ".ehviewer").write_text("1002\ntoken2\n1\n", encoding="utf-8")
    (g2_dir / "0001.jpg").write_bytes(b"y" * 500)

    # 3. 模拟未归档画廊（未在 DB 中设为 cbz）：gid 2001
    g3_dir = dl_dir / "2001-unarchived"
    g3_dir.mkdir()
    (g3_dir / "0001.jpg").write_bytes(b"z" * 200)

    # 4. 模拟活跃下载中的画廊：gid 3001
    g4_dir = dl_dir / "3001-active"
    g4_dir.mkdir()
    (g4_dir / "0001.jpg").write_bytes(b"w" * 300)

    class FakeScalars:
        def __init__(self, data: list[Any]) -> None:
            self._data = data

        def all(self) -> list[Any]:
            return self._data

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def scalars(self, stmt: Any) -> FakeScalars:
            sql = str(stmt)
            if "download_tasks" in sql:
                return FakeScalars([3001])
            if "storage_type" in sql:
                return FakeScalars([1001, 1002])
            if "storage_path" in sql:
                return FakeScalars([str(cold_dir / "cbz" / "1001.cbz"), str(cold_dir / "cbz" / "1002.cbz")])
            return FakeScalars([])

    orig_factory = app_state.session_factory
    try:
        app_state.session_factory = lambda: FakeSession()
        deleted = await purge_archived_sources_internal()
        assert deleted == 2
        assert not g1_dir.exists()
        assert not g2_dir.exists()
        assert g3_dir.exists()
        assert g4_dir.exists()
        assert storage_tracker.downloads.bytes == 4000
    finally:
        app_state.session_factory = orig_factory


def test_purge_archived_sources_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typing import Any

    app_state.settings = Settings(auth_required=False)

    async def fake_purge(*args: Any, **kwargs: Any) -> int:
        return 3

    monkeypatch.setattr("galleryvault.services.cold_archive.purge_archived_sources_internal", fake_purge)

    client = TestClient(app)
    resp = client.post("/api/system/purge-archived-sources")
    assert resp.status_code == 200
    assert resp.json() == {"deleted_dirs": 3}

