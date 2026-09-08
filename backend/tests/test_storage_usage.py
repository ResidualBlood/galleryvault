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
    lib_root = tmp_path / "library"
    lib_root.mkdir()

    # Initial state
    assert tracker.downloads.computing is True
    assert tracker.downloads.bytes is None
    assert tracker.library.computing is True
    assert tracker.library.bytes is None

    # Expected baseline
    dl_base = await measure_dir_bytes(dl_root)
    cache_base = await measure_dir_bytes(cache_root)
    lib_base = await measure_dir_bytes(lib_root)

    # Calibrate roots including library
    await tracker.calibrate(dl_root, cache_root, lib_root)
    assert tracker.downloads.computing is False
    assert tracker.downloads.bytes == dl_base
    assert tracker.cache.bytes == cache_base
    assert tracker.library.bytes == lib_base
    assert tracker.downloads.computed_at is not None
    assert tracker.library.computed_at is not None

    # Deltas after calibration
    tracker.record_download_delta(200)
    tracker.record_download_delta(-50)
    assert tracker.downloads.bytes == dl_base + 150

    tracker.record_cache_delta(30)
    assert tracker.cache.bytes == cache_base + 30

    tracker.record_library_delta(100)
    tracker.record_library_delta(-40)
    assert tracker.library.bytes == lib_base + 60


def test_system_storage_api_fast_and_no_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    storage_tracker.library.bytes = 2048
    storage_tracker.library.computing = False

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

    assert data["library"]["bytes"] == 2048
    assert data["library"]["computing"] is False
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
    import json
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

    storage_tracker.downloads.bytes = 10000
    storage_tracker.library.bytes = 10000

    # 1. 模拟已归档画廊在 dl_dir 的残留文件夹：gid 1001
    g1_dir = dl_dir / "1001-gallery-one"
    g1_dir.mkdir()
    (g1_dir / "0001.jpg").write_bytes(b"x" * 1000)

    # 2. 模拟已归档画廊在 lib_dir 包含 .ehviewer 的残留文件夹：gid 1002
    g2_dir = lib_dir / "gallery-two"
    g2_dir.mkdir()
    (g2_dir / ".ehviewer").write_text("1002\ntoken2\n1\n", encoding="utf-8")
    (g2_dir / "0001.jpg").write_bytes(b"y" * 500)

    # 3. 模拟未归档画廊（未在 DB 中设为 cold storage）：gid 2001
    g3_dir = dl_dir / "2001-unarchived"
    g3_dir.mkdir()
    (g3_dir / "0001.jpg").write_bytes(b"z" * 200)

    # 4. 模拟活跃下载中的画廊：gid 3001
    g4_dir = dl_dir / "3001-active"
    g4_dir.mkdir()
    (g4_dir / "0001.jpg").write_bytes(b"w" * 300)

    # 5. 模拟冷存储 folder 画廊残留（已归档为文件夹形式的大画廊）：gid 1003
    g5_dir = lib_dir / "1003_folder_archive"
    g5_dir.mkdir()
    (g5_dir / ".galleryvault.json").write_text(json.dumps({"gid": 1003}), encoding="utf-8")
    (g5_dir / "0001.jpg").write_bytes(b"f" * 400)

    # 6. 模拟已归档画廊遗留的 .gv- 临时下载目录：gid 1004
    g6_dir = dl_dir / ".gv-1004-tmp"
    g6_dir.mkdir()
    (g6_dir / "temp.bin").write_bytes(b"t" * 600)

    # 7. 模拟活跃下载中正在写入的 .gv- 临时目录：gid 3002（必须安全拦截跳过）
    g7_dir = dl_dir / ".gv-3002-downloading"
    g7_dir.mkdir()
    (g7_dir / "part.bin").write_bytes(b"p" * 700)

    # 8. 模拟包含 JHenTai metadata 文件的已归档画廊残留：gid 1005
    g8_dir = lib_dir / "jhentai-1005"
    g8_dir.mkdir()
    (g8_dir / "metadata").write_text(json.dumps({"gallery": {"gid": 1005}}), encoding="utf-8")
    (g8_dir / "0001.jpg").write_bytes(b"j" * 300)

    # 9. 模拟纯数字目录名的已归档画廊残留：gid 1006
    g9_dir = lib_dir / "1006"
    g9_dir.mkdir()
    (g9_dir / "0001.jpg").write_bytes(b"n" * 250)

    class FakeResult:
        def __init__(self, data: list[Any]) -> None:
            self._data = data

        def all(self) -> list[Any]:
            return self._data

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

        async def execute(self, stmt: Any) -> FakeResult:
            return FakeResult([
                (1001, str(cold_dir / "cbz" / "1001.cbz")),
                (1002, str(cold_dir / "cbz" / "1002.cbz")),
                (1003, str(cold_dir / "folder" / "1003")),  # folder-based cold archive
                (1004, str(cold_dir / "cbz" / "1004.cbz")),
                (1005, str(cold_dir / "cbz" / "1005.cbz")),
                (1006, str(cold_dir / "cbz" / "1006.cbz")),
                (2001, str(dl_dir / "2001-unarchived")),   # Not under cold storage
                (3002, str(cold_dir / "cbz" / "3002.cbz")), # In cold, but currently downloading!
            ])

        async def scalars(self, stmt: Any) -> FakeScalars:
            sql = str(stmt)
            if "download_tasks" in sql:
                # 3001 and 3002 are actively downloading
                return FakeScalars([3001, 3002])
            if "storage_path" in sql:
                return FakeScalars([
                    str(cold_dir / "cbz" / "1001.cbz"),
                    str(cold_dir / "cbz" / "1002.cbz"),
                    str(cold_dir / "folder" / "1003"),
                    str(cold_dir / "cbz" / "1004.cbz"),
                    str(cold_dir / "cbz" / "1005.cbz"),
                    str(cold_dir / "cbz" / "1006.cbz"),
                    str(dl_dir / "2001-unarchived"),
                ])
            return FakeScalars([])

    orig_factory = app_state.session_factory
    try:
        app_state.session_factory = lambda: FakeSession()
        deleted = await purge_archived_sources_internal()
        # 删除了 1001 (dl), 1002 (lib), 1003 (lib folder), 1004 (dl .gv-), 1005 (lib jhentai), 1006 (lib numeric)
        assert deleted == 6
        assert not g1_dir.exists()
        assert not g2_dir.exists()
        assert not g5_dir.exists()
        assert not g6_dir.exists()
        assert not g8_dir.exists()
        assert not g9_dir.exists()

        # 未归档与活跃下载中的必须保留！
        assert g3_dir.exists()
        assert g4_dir.exists()
        assert g7_dir.exists()  # .gv-3002-downloading 被强力前置守卫拦截跳过

        assert storage_tracker.downloads.bytes < 10000
        assert storage_tracker.library.bytes < 10000
    finally:
        app_state.session_factory = orig_factory


def test_purge_archived_sources_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typing import Any

    from galleryvault.app.dependencies import get_task_manager

    app_state.settings = Settings(auth_required=False)
    tm = get_task_manager()
    state = tm._resolve_task_state("purge-archived-sources")
    state["running"] = False

    async def fake_purge(*args: Any, **kwargs: Any) -> int:
        return 3

    monkeypatch.setattr("galleryvault.services.cold_archive.run_purge_archived_sources", fake_purge)

    client = TestClient(app)
    resp = client.post("/api/system/purge-archived-sources")
    assert resp.status_code == 202
    assert resp.json() == {"status": "started"}

    # Second call while running -> re-entrance prevention
    state["running"] = True
    resp2 = client.post("/api/system/purge-archived-sources")
    assert resp2.status_code == 202
    assert resp2.json() == {"status": "running"}
    state["running"] = False


@pytest.mark.asyncio
async def test_run_purge_archived_sources_task_flow(tmp_path: Path) -> None:
    from typing import Any

    from galleryvault.services.cold_archive import run_purge_archived_sources
    from galleryvault.services.tasks import TaskManager

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

        async def execute(self, stmt: Any) -> FakeScalars:
            return FakeScalars([])

        async def scalars(self, stmt: Any) -> FakeScalars:
            return FakeScalars([])

    tm = TaskManager()
    calibrated = []

    async def fake_calibrate(*args: Any, **kwargs: Any) -> None:
        calibrated.append(True)

    orig_calib = storage_tracker.calibrate
    storage_tracker.calibrate = fake_calibrate  # type: ignore[assignment]
    try:
        purged = await run_purge_archived_sources(tm=tm, session_factory=lambda: FakeSession())
        assert isinstance(purged, int)
        assert len(calibrated) == 1
        assert any(t.get("task") == "purge-archived-sources" for t in tm.task_history)
    finally:
        storage_tracker.calibrate = orig_calib


@pytest.mark.asyncio
async def test_purge_archived_sources_no_truncation_and_safety_lock(tmp_path: Path) -> None:
    import json
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

    # 1. 活跃路径目录 active_parent，里面嵌套了一个已归档残留 4001
    active_parent = lib_dir / "active_parent"
    active_parent.mkdir()
    nested_archived = active_parent / " 4001 - nested_archived "
    nested_archived.mkdir()
    (nested_archived / "0001.jpg").write_bytes(b"data")

    # 2. 活跃下载任务的 .gv- 临时目录：gid 5001
    active_gv_dir = dl_dir / ".gv-5001-downloading"
    active_gv_dir.mkdir()
    (active_gv_dir / "0001.tmp").write_bytes(b"active-downloading-data")

    # 3. JHenTai 根级 gid metadata 的残留：gid 4002
    jhentai_dir = lib_dir / "jhentai_root"
    jhentai_dir.mkdir()
    (jhentai_dir / "metadata").write_text(json.dumps({"gid": 4002}), encoding="utf-8")
    (jhentai_dir / "0001.jpg").write_bytes(b"data")

    class FakeResult:
        def __init__(self, data: list[Any]) -> None:
            self._data = data

        def all(self) -> list[Any]:
            return self._data

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

        async def execute(self, stmt: Any) -> FakeResult:
            return FakeResult([
                (4001, str(cold_dir / "folder" / "4001")),
                (4002, str(cold_dir / "cbz" / "4002.cbz")),
            ])

        async def scalars(self, stmt: Any) -> FakeScalars:
            sql = str(stmt)
            if "download_tasks" in sql:
                return FakeScalars([5001])
            if "storage_path" in sql:
                # active_parent 本身是某画廊的 storage_path
                return FakeScalars([str(active_parent)])
            return FakeScalars([])

    orig_factory = app_state.session_factory
    try:
        app_state.session_factory = lambda: FakeSession()
        deleted = await purge_archived_sources_internal()
        assert deleted == 2
        # active_parent 本身未被删
        assert active_parent.exists()
        # nested_archived 子目录未被截断，且已被成功删除
        assert not nested_archived.exists()
        # active_gv_dir 处于 active_dl_gids，绝对不能被删除
        assert active_gv_dir.exists()
        # jhentai_dir 成功清理
        assert not jhentai_dir.exists()
    finally:
        app_state.session_factory = orig_factory
