import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

from galleryvault.services.cold_archive import (
    COLD_ARCHIVE_MAX_CBZ_BYTES,
    ColdAlreadyArchivedError,
    ColdDestinationExistsError,
    cold_pack_gallery,
    cold_partition,
    compute_cold_path,
    safe_title,
)
from galleryvault.services.export_cbz import ZIP_STORED, page_archive_name


def test_constants_and_safe_title() -> None:
    assert COLD_ARCHIVE_MAX_CBZ_BYTES == 2 * 1024 * 1024 * 1024
    assert safe_title('a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i"
    assert safe_title("   ") == "gallery"
    assert safe_title(None) == "gallery"


def test_cold_partition_uses_sha256_not_mod256() -> None:
    gid = 257  # 257 % 256 == 1, but sha256("257") is not 00/01
    hh, ii = cold_partition(gid=gid)
    expected_digest = hashlib.sha256(str(gid).encode("utf-8")).hexdigest()
    assert hh == expected_digest[:2]
    assert ii == expected_digest[2:4]
    assert (hh, ii) != ("00", "01")

    # Stable path_hash
    sample_hash = "abcdef1234567890" * 4
    hh_s, ii_s = cold_partition(stable=sample_hash)
    assert hh_s == sample_hash[:2]
    assert ii_s == sample_hash[2:4]


def test_compute_cold_path_shapes(tmp_path: Path) -> None:
    cold_root = tmp_path / "cold"
    gid = 12345
    h = hashlib.sha256(b"12345").hexdigest()
    hh, ii = h[:2], h[2:4]

    # gid + cbz
    p_cbz = compute_cold_path(cold_root, is_cbz=True, gid=gid, title="My Gallery")
    assert p_cbz == cold_root / "cbz" / hh / ii / "12345-My Gallery.cbz"

    # gid + dir
    p_dir = compute_cold_path(cold_root, is_cbz=False, gid=gid, title="My Gallery")
    assert p_dir == cold_root / "dir" / hh / ii / "12345"

    # ungid + cbz
    stable = "1122334455667788" * 4
    p_ungid_cbz = compute_cold_path(cold_root, is_cbz=True, stable=stable, title="Local")
    assert p_ungid_cbz == cold_root / "ungid" / "11" / "22" / f"{stable}-Local.cbz"

    # ungid + dir
    p_ungid_dir = compute_cold_path(cold_root, is_cbz=False, stable=stable, title="Local")
    assert p_ungid_dir == cold_root / "ungid" / "11" / "22" / f"{stable}-Local"


def test_small_dir_packs_to_cbz_triplet_and_filters_forbidden(tmp_path: Path) -> None:
    source = tmp_path / "12345-Test Gallery"
    source.mkdir()

    # Image files
    (source / "01.jpg").write_bytes(b"image-data-1")
    (source / "02.png").write_bytes(b"image-data-2")

    # Forbidden files that MUST NOT appear in cold archive
    (source / "cover.jpg").write_bytes(b"forbidden-cover")
    (source / ".ehviewer").write_text("VERSION1\n0\n12345\ntok123\n0\n0\n2\n0 ptok1\n1 ptok2\n")
    (source / "metadata.json").write_text('{"title": "jhentai"}')

    cold_root = tmp_path / "cold"
    dest = cold_pack_gallery(
        source=source,
        cold_root=cold_root,
        gid=12345,
        token="tok123",
        title="Test Gallery",
        tags=[{"namespace": "artist", "name": "alice"}, "female:sole female"],
        p_tokens=["ptok1", "ptok2"],
    )

    assert dest.is_file()
    assert dest.suffix == ".cbz"
    expected_path = compute_cold_path(cold_root, is_cbz=True, gid=12345, title="Test Gallery")
    assert dest == expected_path

    # Verify CBZ contents: ONLY 0001.ext..., ComicInfo.xml, .galleryvault.json
    with zipfile.ZipFile(dest, "r") as zf:
        namelist = sorted(zf.namelist())
        assert namelist == [".galleryvault.json", "0001.jpg", "0002.png", "ComicInfo.xml"]

        # Check STORED compression
        for name in ["0001.jpg", "0002.png"]:
            assert zf.getinfo(name).compress_type == ZIP_STORED

        assert zf.read("0001.jpg") == b"image-data-1"
        assert zf.read("0002.png") == b"image-data-2"

        # Verify .galleryvault.json
        gv_data = json.loads(zf.read(".galleryvault.json").decode("utf-8"))
        assert gv_data["gid"] == 12345
        assert gv_data["token"] == "tok123"
        assert gv_data["p_tokens"] == ["ptok1", "ptok2"]
        assert gv_data["tags"] == [
            {"namespace": "artist", "name": "alice"},
            {"namespace": "female", "name": "sole female"},
        ]

        # Verify ComicInfo.xml
        root = ElementTree.fromstring(zf.read("ComicInfo.xml"))
        assert root.tag == "ComicInfo"
        assert root.findtext("Title") == "Test Gallery"
        assert root.findtext("PageCount") == "2"
        assert root.findtext("Writer") == "alice"
        assert "artist:alice" in (root.findtext("Genre") or "")
        assert "female:sole female" in (root.findtext("Genre") or "")
        assert root.findtext("Web") == "https://exhentai.org/g/12345/tok123/"


def test_large_dir_packs_to_directory_forbidding_zip(tmp_path: Path) -> None:
    source = tmp_path / "large-gallery"
    source.mkdir()
    (source / "p1.jpg").write_bytes(b"x" * 50)
    (source / "p2.jpg").write_bytes(b"y" * 60)
    # Total page bytes: 110 bytes

    cold_root = tmp_path / "cold"
    # Set max_cbz_bytes = 100 so 110 bytes triggers directory packing
    dest = cold_pack_gallery(
        source=source,
        cold_root=cold_root,
        gid=99999,
        title="Large One",
        max_cbz_bytes=100,
    )

    assert dest.is_dir()
    expected_path = compute_cold_path(cold_root, is_cbz=False, gid=99999, title="Large One")
    assert dest == expected_path

    # Verify directory contents: ONLY 0001.ext..., ComicInfo.xml, .galleryvault.json
    entries = sorted([p.name for p in dest.iterdir()])
    assert entries == [".galleryvault.json", "0001.jpg", "0002.jpg", "ComicInfo.xml"]

    assert (dest / "0001.jpg").read_bytes() == b"x" * 50
    assert (dest / "0002.jpg").read_bytes() == b"y" * 60
    assert (dest / "ComicInfo.xml").is_file()
    assert (dest / ".galleryvault.json").is_file()


def test_failure_cleans_partial_and_does_not_delete_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source-gallery"
    source.mkdir()
    p1 = source / "01.jpg"
    p2 = source / "02.jpg"
    p1.write_bytes(b"data-1")
    p2.write_bytes(b"data-2")

    cold_root = tmp_path / "cold"

    # Simulate error during zip writing
    def boom_write(*args, **kwargs):
        raise OSError("Disk simulated write error")

    monkeypatch.setattr(zipfile.ZipFile, "write", boom_write)

    with pytest.raises(OSError, match="Disk simulated write error"):
        cold_pack_gallery(
            source=source,
            cold_root=cold_root,
            gid=777,
            title="Fail Gallery",
            delete_source=True,  # Even with delete_source=True, failure MUST NOT delete source
        )

    # Destination MUST NOT exist
    dest = compute_cold_path(cold_root, is_cbz=True, gid=777, title="Fail Gallery")
    assert not dest.exists()

    # Partial file MUST be cleaned up
    partial = dest.parent / f"{dest.name}.partial"
    assert not partial.exists()

    # Source MUST be completely intact
    assert source.is_dir()
    assert p1.is_file() and p1.read_bytes() == b"data-1"
    assert p2.is_file() and p2.read_bytes() == b"data-2"


def test_failure_on_directory_pack_cleans_partial_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil

    source = tmp_path / "source-dir-fail"
    source.mkdir()
    (source / "01.jpg").write_bytes(b"page1")

    cold_root = tmp_path / "cold"

    def boom_copy(*args, **kwargs):
        raise OSError("Copy failed midway")

    monkeypatch.setattr(shutil, "copy2", boom_copy)

    with pytest.raises(OSError, match="Copy failed midway"):
        cold_pack_gallery(
            source=source,
            cold_root=cold_root,
            gid=888,
            title="Fail Dir Gallery",
            max_cbz_bytes=1,  # Force directory
            delete_source=True,
        )

    dest = compute_cold_path(cold_root, is_cbz=False, gid=888, title="Fail Dir Gallery")
    assert not dest.exists()
    partial = dest.parent / f"{dest.name}.partial"
    assert not partial.exists()

    # Source unchanged
    assert source.is_dir()
    assert (source / "01.jpg").read_bytes() == b"page1"


def test_ungid_packing_cbz_and_dir(tmp_path: Path) -> None:
    source = tmp_path / "local-folder"
    source.mkdir()
    (source / "img1.png").write_bytes(b"png1")
    (source / "img2.png").write_bytes(b"png2")

    cold_root = tmp_path / "cold"
    stable_hash = "f" * 64

    # Ungid small -> CBZ
    dest_cbz = cold_pack_gallery(
        source=source,
        cold_root=cold_root,
        title="Ungid Comic",
        stable=stable_hash,
    )
    assert dest_cbz.is_file()
    assert dest_cbz.suffix == ".cbz"
    assert "ungid" in dest_cbz.parts
    assert dest_cbz.name == f"{stable_hash}-Ungid Comic.cbz"

    # Ungid large -> Dir
    dest_dir = cold_pack_gallery(
        source=source,
        cold_root=cold_root,
        title="Ungid Comic Big",
        stable=stable_hash,
        max_cbz_bytes=2,  # Force dir
    )
    assert dest_dir.is_dir()
    assert "ungid" in dest_dir.parts
    assert dest_dir.name == f"{stable_hash}-Ungid Comic Big"


def test_rejects_already_in_cold_and_existing_dest(tmp_path: Path) -> None:
    cold_root = tmp_path / "cold"
    cold_root.mkdir()

    # Create gallery inside cold root
    in_cold = cold_root / "my-gallery"
    in_cold.mkdir()
    (in_cold / "1.jpg").write_bytes(b"1")

    with pytest.raises(ColdAlreadyArchivedError):
        cold_pack_gallery(source=in_cold, cold_root=cold_root, gid=111)

    # Outside cold root
    source = tmp_path / "outside"
    source.mkdir()
    (source / "1.jpg").write_bytes(b"1")

    dest = cold_pack_gallery(source=source, cold_root=cold_root, gid=111, title="Test")
    assert dest.exists()

    # Pack again -> ColdDestinationExistsError
    with pytest.raises(ColdDestinationExistsError):
        cold_pack_gallery(source=source, cold_root=cold_root, gid=111, title="Test")


def test_helper_page_archive_name() -> None:
    assert page_archive_name(1, ".jpg") == "0001.jpg"
    assert page_archive_name(2, "png") == "0002.png"
    assert page_archive_name(10, None) == "0010.jpg"
    assert page_archive_name(12345, ".webp") == "12345.webp"


# --- T3 Tests: TaskManager, Endpoints, and run_cold_archive / archive_one ---


def test_task_manager_archive_state_and_summary() -> None:
    from galleryvault.services.tasks import TaskManager

    tm = TaskManager()
    assert "archive_state" in dir(tm)
    assert tm.archive_state["running"] is False
    assert tm.archive_state["done"] == 0
    assert tm.archive_state["total"] == 0

    # Summary when not running
    summary = tm.get_running_summary()
    assert not any(t["task"] == "archive" for t in summary)

    # Summary when running
    tm.archive_state["running"] = True
    tm.archive_state["started_at"] = "2026-09-05T12:00:00Z"
    tm.archive_state["done"] = 5
    tm.archive_state["total"] = 10
    summary = tm.get_running_summary()
    archive_task = next((t for t in summary if t["task"] == "archive"), None)
    assert archive_task is not None
    assert archive_task["cancellable"] is True
    assert archive_task["done"] == 5
    assert archive_task["total"] == 10


@pytest.mark.asyncio
async def test_router_archive_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    from galleryvault.app.routers.tasks import (
        archive_status,
        cancel_background_task,
        trigger_archive,
    )
    from galleryvault.app.state import app_state
    from galleryvault.config import Settings
    from galleryvault.services.tasks import default_task_manager

    # 1. No cold root -> 422
    app_state.settings = Settings(cold_storage_root="")
    with pytest.raises(HTTPException) as exc_info:
        await trigger_archive()
    assert exc_info.value.status_code == 422

    # 2. Global paused -> status: paused
    app_state.settings = Settings(cold_storage_root="/cold", global_paused=True)
    res_paused = await trigger_archive()
    assert res_paused["status"] == "paused"

    # 3. Already running -> status: running
    app_state.settings = Settings(cold_storage_root="/cold", global_paused=False)
    default_task_manager.archive_state["running"] = True
    res_running = await trigger_archive()
    assert res_running["status"] == "running"
    default_task_manager.archive_state["running"] = False

    # 4. Trigger starts task -> status: started (202)
    spawned = []

    def fake_spawn(coro, op):
        spawned.append(op)
        coro.close()

    monkeypatch.setattr("galleryvault.app.routers.tasks.spawn_task", fake_spawn)
    res_started = await trigger_archive()
    assert res_started["status"] == "started"
    assert default_task_manager.archive_state["running"] is True
    assert "cold archive" in spawned
    default_task_manager.archive_state["running"] = False

    # 5. GET /api/archive -> archive_state
    status = await archive_status()
    assert "running" in status
    assert "done" in status

    # 6. POST /api/logs/{task}/cancel allowlist includes archive
    res_cancel = await cancel_background_task("archive")
    assert res_cancel == {"task": "archive", "status": "cancelling"}
    assert default_task_manager.is_cancelled("archive") is True
    default_task_manager.clear_cancelled("archive")

    # Unknown task still 404
    with pytest.raises(HTTPException) as exc_404:
        await cancel_background_task("unknown_task")
    assert exc_404.value.status_code == 404


@pytest.mark.asyncio
async def test_archive_one_space_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    from types import SimpleNamespace

    from galleryvault.services.cold_archive import archive_one

    cold_root = tmp_path / "cold"
    cold_root.mkdir()

    source = tmp_path / "ssd" / "gallery1"
    source.mkdir(parents=True)
    (source / "01.jpg").write_bytes(b"data")

    # Mock DB session returning a Gallery with size 1000
    gallery_mock = SimpleNamespace(
        id=42,
        gid=123,
        token="tok",
        title="Space Test",
        storage_path=str(source),
        storage_size=1000,
        file_size=1000,
        trashed=False,
        path_hash="dummyhash",
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, model, ident):
            return gallery_mock if ident == 42 else None

        async def scalar(self, stmt):
            return None

        async def execute(self, stmt):
            class Res:
                def all(self):
                    return []

            return Res()

        async def commit(self):
            pass

    # Mock disk_usage to return tiny free space (e.g. 10 bytes < 1000 * 1.2)
    monkeypatch.setattr(
        shutil, "disk_usage", lambda path: SimpleNamespace(total=10000, used=9990, free=10)
    )

    dest = await archive_one(
        42,
        cold_root=cold_root,
        session_factory=lambda: FakeSession(),
    )
    # Must be skipped due to insufficient space
    assert dest is None
    # Source still exists
    assert source.exists()


@pytest.mark.asyncio
async def test_run_cold_archive_cancellation_and_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from galleryvault.app.state import app_state
    from galleryvault.config import Settings
    from galleryvault.services.cold_archive import run_cold_archive
    from galleryvault.services.tasks import TaskManager

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    ssd_root = tmp_path / "ssd"
    ssd_root.mkdir()

    # Gallery 1: in SSD root
    g1_dir = ssd_root / "101-G1"
    g1_dir.mkdir()
    (g1_dir / "01.jpg").write_bytes(b"image")

    # Gallery 2: in SSD root
    g2_dir = ssd_root / "102-G2"
    g2_dir.mkdir()
    (g2_dir / "01.jpg").write_bytes(b"image")

    # Gallery 3: already under cold (should not be candidate)
    g3_dir = cold_root / "cbz" / "already"
    g3_dir.mkdir(parents=True)
    (g3_dir / "01.jpg").write_bytes(b"image")

    tm = TaskManager()
    app_state.settings = Settings(
        cold_storage_root=str(cold_root),
        library_roots=[str(ssd_root)],
        archive_delete_source=True,
    )

    galleries = [
        SimpleNamespace(id=1, gid=101, storage_path=str(g1_dir), trashed=False, storage_size=10),
        SimpleNamespace(id=2, gid=102, storage_path=str(g2_dir), trashed=False, storage_size=10),
        SimpleNamespace(id=3, gid=103, storage_path=str(g3_dir), trashed=False, storage_size=10),
    ]

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def scalars(self, stmt):
            class Res:
                def all(self):
                    return []  # No active download tasks

            return Res()

        async def execute(self, stmt):
            class Res:
                def all(self):
                    # Return candidates query: (id, gid, storage_path)
                    return [(g.id, g.gid, g.storage_path) for g in galleries]

            return Res()

        async def get(self, model, ident):
            for g in galleries:
                if g.id == ident:
                    return g
            return None

        async def commit(self):
            pass

    # Cancel after 1 gallery
    call_count = 0

    async def fake_archive_one(gid_or_id, **kwargs):
        nonlocal call_count
        call_count += 1
        # Trigger cancel during first item
        tm.request_cancel("archive")
        return cold_root / "fake_dest.cbz"

    monkeypatch.setattr("galleryvault.services.cold_archive.archive_one", fake_archive_one)

    await run_cold_archive(
        session_factory=lambda: FakeSession(),
        task_manager=tm,
    )

    # 3 galleries total, but g3 is in cold, so candidates were [1, 2]
    assert tm.archive_state["total"] == 2
    # Stopped after 1 item because cancelled between items
    assert call_count == 1
    assert tm.archive_state["running"] is False
    assert len(tm.task_history) == 1
    assert tm.task_history[0]["status"] == "cancelled"
    assert "cancelled" in tm.task_history[0]["reason"]


@pytest.mark.asyncio
async def test_archive_one_e2e_packs_updates_db_and_deletes_source(tmp_path: Path) -> None:
    from galleryvault.services.cold_archive import archive_one

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    ssd_root = tmp_path / "ssd"
    ssd_root.mkdir()

    source = ssd_root / "200-My E2E Gallery"
    source.mkdir()
    (source / "01.jpg").write_bytes(b"page1")
    (source / "02.png").write_bytes(b"page2")

    class FakeGallery:
        def __init__(self):
            self.id = 55
            self.gid = 200
            self.token = "tok200"
            self.title = "My E2E Gallery"
            self.storage_path = str(source)
            self.storage_type = "folder"
            self.storage_size = 10
            self.file_size = 10
            self.trashed = False
            self.path_hash = "oldhash"
            self.page_count = 2
            self.cover_path = "01.jpg"

    gallery_obj = FakeGallery()
    pages_created = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, model, ident):
            from galleryvault.db.models import Gallery

            if model is Gallery and ident == 55:
                return gallery_obj
            return None

        async def scalar(self, stmt):
            return None

        async def execute(self, stmt):
            class Res:
                def all(self):
                    return []

            return Res()

        def add_all(self, items):
            pages_created.extend(items)

        async def commit(self):
            pass

    dest = await archive_one(
        55,
        cold_root=cold_root,
        delete_source=True,
        session_factory=lambda: FakeSession(),
    )

    assert dest is not None
    assert dest.is_file()
    assert dest.suffix == ".cbz"
    # Source was deleted
    assert not source.exists()
    # Gallery properties were updated
    assert gallery_obj.storage_path == str(dest)
    assert gallery_obj.storage_type == "cbz"
    assert gallery_obj.page_count == 2
    assert gallery_obj.cover_path == "0001.jpg"
    assert len(pages_created) == 2
    assert pages_created[0].member_name == "0001.jpg"
    assert pages_created[1].member_name == "0002.png"

    # Running archive_one again should skip because it's now in cold
    dest_again = await archive_one(
        55,
        cold_root=cold_root,
        delete_source=True,
        session_factory=lambda: FakeSession(),
    )
    assert dest_again is None


# --- T5 Tests: Download Archive Hook & archive_status ---


@pytest.mark.asyncio
async def test_download_repository_archive_status() -> None:
    from galleryvault.db.models import DownloadTask
    from galleryvault.db.repositories.downloads import DownloadRepository

    task = DownloadTask(
        id=101,
        gid=9991,
        token="tok1",
        status="success",
        archive_status=None,
        archive_error=None,
    )

    class FakeSession:
        async def get(self, model, ident):
            if model is DownloadTask and ident == 101:
                return task
            return None

        async def scalar(self, stmt):
            return task

        async def flush(self):
            pass

    repo = DownloadRepository(FakeSession())

    # Update to pending
    res = await repo.update_archive_status(9991, "pending", None)
    assert res is True
    assert task.archive_status == "pending"
    assert task.archive_error is None

    # Update to ok
    res = await repo.update_archive_status(9991, "ok", None)
    assert res is True
    assert task.archive_status == "ok"
    assert task.archive_error is None

    # Update to fail with error
    res = await repo.update_archive_status(9991, "fail", "disk space insufficient")
    assert res is True
    assert task.archive_status == "fail"
    assert task.archive_error == "disk space insufficient"
    # download status itself remains success
    assert task.status == "success"


@pytest.mark.asyncio
async def test_downloads_route_includes_archive_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers.downloads import list_downloads
    from galleryvault.db.models import DownloadTask

    t1 = DownloadTask(
        id=1,
        gid=1001,
        token="tok1",
        title="Gallery 1",
        status="success",
        current_page=10,
        total_pages=10,
        archive_status="ok",
        archive_error=None,
    )
    t2 = DownloadTask(
        id=2,
        gid=1002,
        token="tok2",
        title="Gallery 2",
        status="success",
        current_page=10,
        total_pages=10,
        archive_status="fail",
        archive_error="space exceeded",
    )
    t3 = DownloadTask(
        id=3,
        gid=1003,
        token="tok3",
        title="Gallery 3",
        status="downloading",
        current_page=2,
        total_pages=10,
        archive_status=None,
        archive_error=None,
    )

    class FakeRepo:
        def __init__(self, _session):
            pass

        async def list_page(self, page, page_size, status):
            return 3, [t1, t2, t3]

    async def fake_get_session():
        yield None

    monkeypatch.setattr("galleryvault.app.routers.downloads.DownloadRepository", FakeRepo)
    monkeypatch.setattr("galleryvault.app.routers.downloads.get_session", fake_get_session)

    res = await list_downloads()
    items = res["items"]
    assert len(items) == 3

    assert items[0]["archive_status"] == "ok"
    assert items[0]["archive_error"] is None

    assert items[1]["archive_status"] == "fail"
    assert items[1]["archive_error"] == "space exceeded"

    assert items[2]["archive_status"] is None
    assert items[2]["archive_error"] is None


@pytest.mark.asyncio
async def test_ingest_downloaded_gallery_hook_triggers_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from galleryvault.app.state import app_state
    from galleryvault.db.models import DownloadTask
    from galleryvault.services import download_worker

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    ssd_root = tmp_path / "ssd"
    ssd_root.mkdir()

    gallery_dir = ssd_root / "1234-Test Archive Ingest"
    gallery_dir.mkdir()
    (gallery_dir / "0001.jpg").write_bytes(b"image content")

    task_row = DownloadTask(
        id=5,
        gid=1234,
        token="tok1234",
        title="Test Archive Ingest",
        status="success",
        archive_status=None,
        archive_error=None,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def get(self, model, ident):
            if model is DownloadTask and ident == 5:
                return task_row
            return None

        async def scalar(self, stmt):
            if "download_tasks" in str(stmt):
                return task_row
            return None

        async def flush(self):
            pass

        async def commit(self):
            pass

    class FakeIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, galleries):
            pass

    class FakeScanner:
        storage_type = "folder"
        def storage_signature(self, p):
            return "sig"

    archive_called = []

    async def fake_archive_one(gid, **kwargs):
        archive_called.append(gid)
        return cold_root / "cbz/00/00/1234.cbz"

    orig_factory = app_state.session_factory
    orig_settings = app_state.settings
    app_state.session_factory = lambda: FakeSession()
    app_state.settings = SimpleNamespace(
        auto_archive_downloads=True,
        cold_storage_root=str(cold_root),
        archive_delete_source=True,
    )

    spawned_tasks = []
    def fake_spawn_task(coro, op):
        spawned_tasks.append(coro)

    monkeypatch.setattr(download_worker, "GalleryIngestService", FakeIngest)
    monkeypatch.setattr(download_worker, "registry", SimpleNamespace(for_path=lambda p: FakeScanner()))
    monkeypatch.setattr("galleryvault.app.dependencies.spawn_task", fake_spawn_task)
    monkeypatch.setattr("galleryvault.services.cold_archive.archive_one", fake_archive_one)

    try:
        result = SimpleNamespace(
            gid=1234,
            token="tok1234",
            path=gallery_dir,
            title="Test Archive Ingest",
            quality="original",
            pages=1,
            tags=[],
        )
        await download_worker.ingest_downloaded_gallery(result)

        # Before background archive task runs, task_row archive_status was pre-marked pending
        assert task_row.archive_status == "pending"

        # Run the spawned archive coroutine
        assert len(spawned_tasks) == 1
        await spawned_tasks[0]

        # After background task completes
        assert len(archive_called) == 1
        assert archive_called[0] == 1234
        assert task_row.archive_status == "ok"
        assert task_row.archive_error is None
        assert task_row.status == "success"
    finally:
        app_state.session_factory = orig_factory
        app_state.settings = orig_settings


@pytest.mark.asyncio
async def test_archive_failure_does_not_fail_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from galleryvault.app.state import app_state
    from galleryvault.db.models import DownloadTask
    from galleryvault.services import download_worker

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    ssd_root = tmp_path / "ssd"
    ssd_root.mkdir()

    gallery_dir = ssd_root / "5678-Fail Archive Ingest"
    gallery_dir.mkdir()
    (gallery_dir / "0001.jpg").write_bytes(b"image content")

    task_row = DownloadTask(
        id=6,
        gid=5678,
        token="tok5678",
        title="Fail Archive Ingest",
        status="success",
        archive_status=None,
        archive_error=None,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def get(self, model, ident):
            if model is DownloadTask and ident == 6:
                return task_row
            return None

        async def scalar(self, stmt):
            if "download_tasks" in str(stmt):
                return task_row
            return None

        async def flush(self):
            pass

        async def commit(self):
            pass

    class FakeIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, galleries):
            pass

    class FakeScanner:
        storage_type = "folder"
        def storage_signature(self, p):
            return "sig"

    async def fake_archive_one_fail(gid, **kwargs):
        raise RuntimeError("No space left on device")

    orig_factory = app_state.session_factory
    orig_settings = app_state.settings
    app_state.session_factory = lambda: FakeSession()
    app_state.settings = SimpleNamespace(
        auto_archive_downloads=True,
        cold_storage_root=str(cold_root),
        archive_delete_source=True,
    )

    spawned_tasks = []
    def fake_spawn_task(coro, op):
        spawned_tasks.append(coro)

    monkeypatch.setattr(download_worker, "GalleryIngestService", FakeIngest)
    monkeypatch.setattr(download_worker, "registry", SimpleNamespace(for_path=lambda p: FakeScanner()))
    monkeypatch.setattr("galleryvault.app.dependencies.spawn_task", fake_spawn_task)
    monkeypatch.setattr("galleryvault.services.cold_archive.archive_one", fake_archive_one_fail)

    try:
        result = SimpleNamespace(
            gid=5678,
            token="tok5678",
            path=gallery_dir,
            title="Fail Archive Ingest",
            quality="original",
            pages=1,
            tags=[],
        )
        await download_worker.ingest_downloaded_gallery(result)

        assert len(spawned_tasks) == 1
        await spawned_tasks[0]

        # Crucial requirements:
        # 1. archive_status is fail and error is saved
        assert task_row.archive_status == "fail"
        assert "No space left on device" in (task_row.archive_error or "")
        # 2. Download status MUST REMAIN SUCCESS (not changed to failed)
        assert task_row.status == "success"
    finally:
        app_state.session_factory = orig_factory
        app_state.settings = orig_settings


@pytest.mark.asyncio
async def test_ingest_downloaded_gallery_hook_skips_archive_when_disabled_or_no_cold_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from galleryvault.app.state import app_state
    from galleryvault.db.models import DownloadTask
    from galleryvault.services import download_worker

    ssd_root = tmp_path / "ssd"
    ssd_root.mkdir()
    gallery_dir = ssd_root / "9999-Skip Archive Ingest"
    gallery_dir.mkdir()
    (gallery_dir / "0001.jpg").write_bytes(b"image")

    task_row = DownloadTask(
        id=7,
        gid=9999,
        token="tok9999",
        title="Skip Archive Ingest",
        status="success",
        archive_status=None,
        archive_error=None,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def scalar(self, stmt):
            if "download_tasks" in str(stmt):
                return task_row
            return None

        async def flush(self):
            pass

    spawned = []
    monkeypatch.setattr(download_worker, "GalleryIngestService", lambda s: SimpleNamespace(ingest=lambda g: None))
    monkeypatch.setattr(download_worker, "registry", SimpleNamespace(for_path=lambda p: SimpleNamespace(storage_type="folder", storage_signature=lambda p: "sig")))
    monkeypatch.setattr("galleryvault.app.dependencies.spawn_task", lambda coro, op: spawned.append(op))

    orig_factory = app_state.session_factory
    orig_settings = app_state.settings
    app_state.session_factory = lambda: FakeSession()

    # Case A: auto_archive_downloads is False
    app_state.settings = SimpleNamespace(
        auto_archive_downloads=False,
        cold_storage_root=str(tmp_path / "cold"),
    )
    result = SimpleNamespace(
        gid=9999,
        token="tok9999",
        path=gallery_dir,
        title="Skip Archive Ingest",
        quality="original",
        pages=1,
        tags=[],
    )
    try:
        await download_worker.ingest_downloaded_gallery(result)
        assert len(spawned) == 0
        assert task_row.archive_status is None

        # Case B: cold_storage_root is empty
        app_state.settings = SimpleNamespace(
            auto_archive_downloads=True,
            cold_storage_root="",
        )
        await download_worker.ingest_downloaded_gallery(result)
        assert len(spawned) == 0
        assert task_row.archive_status is None
    finally:
        app_state.session_factory = orig_factory
        app_state.settings = orig_settings


@pytest.mark.asyncio
async def test_archive_hook_error_does_not_break_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from galleryvault.app.state import app_state
    from galleryvault.services import download_worker

    ssd_root = tmp_path / "ssd"
    ssd_root.mkdir()
    gallery_dir = ssd_root / "8888-Hook Crash"
    gallery_dir.mkdir()
    (gallery_dir / "0001.jpg").write_bytes(b"image")

    class FakeIngest:
        def __init__(self, _session):
            pass

        async def ingest(self, galleries):
            pass

    monkeypatch.setattr(download_worker, "GalleryIngestService", FakeIngest)
    monkeypatch.setattr(download_worker, "registry", SimpleNamespace(for_path=lambda p: SimpleNamespace(storage_type="folder", storage_signature=lambda p: "sig")))

    def exploding_spawn(coro, op):
        if hasattr(coro, "close"):
            coro.close()
        raise RuntimeError("spawn crashed completely")

    monkeypatch.setattr("galleryvault.app.dependencies.spawn_task", exploding_spawn)

    orig_settings = app_state.settings
    app_state.settings = SimpleNamespace(
        auto_archive_downloads=True,
        cold_storage_root=str(tmp_path / "cold"),
    )
    result = SimpleNamespace(
        gid=8888,
        token="tok8888",
        path=gallery_dir,
        title="Hook Crash",
        quality="original",
        pages=1,
        tags=[],
    )
    try:
        # ingest_downloaded_gallery MUST NOT raise an unhandled exception
        await download_worker.ingest_downloaded_gallery(result)
    finally:
        app_state.settings = orig_settings


@pytest.mark.asyncio
async def test_run_cold_archive_notifications(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from galleryvault.app.state import app_state
    from galleryvault.services.cold_archive import run_cold_archive
    from galleryvault.services.notifications import clear_notifications, list_notifications
    from galleryvault.services.tasks import TaskManager

    clear_notifications()
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    ssd_root = tmp_path / "ssd"
    ssd_root.mkdir()

    app_state.settings = SimpleNamespace(
        cold_storage_root=str(cold_root),
        global_paused=False,
        telegram_notify_level="immediate",
        telegram_notify_lang="zh",
        telegram_bot_token=None,
    )
    monkeypatch.setattr("galleryvault.app.dependencies.get_scan_roots", lambda: [str(ssd_root)])

    galleries = [
        SimpleNamespace(id=1, gid=101, storage_path=str(ssd_root / "g1")),
        SimpleNamespace(id=2, gid=102, storage_path=str(ssd_root / "g2")),
    ]
    (ssd_root / "g1").mkdir()
    (ssd_root / "g2").mkdir()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def scalars(self, stmt):
            class Res:
                def all(self):
                    return []

            return Res()

        async def execute(self, stmt):
            class Res:
                def all(self):
                    return [(g.id, g.gid, g.storage_path) for g in galleries]

            return Res()

    tm = TaskManager()

    # Scenario 1: All success -> archive_start + archive_ok
    async def fake_archive_ok(gid_or_id, **kwargs):
        return cold_root / "dest.cbz"

    monkeypatch.setattr("galleryvault.services.cold_archive.archive_one", fake_archive_ok)
    await run_cold_archive(session_factory=lambda: FakeSession(), task_manager=tm)

    data = list_notifications()
    assert data["unread_count"] == 2
    # items are in reverse order (newest first)
    kinds = [item["kind"] for item in reversed(data["items"])]
    assert kinds == ["archive_start", "archive_ok"]

    # Scenario 2: With failure -> archive_start + archive_fail
    clear_notifications()
    call_idx = 0

    async def fake_archive_fail(gid_or_id, **kwargs):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return cold_root / "dest.cbz"
        raise RuntimeError("disk read failed")

    monkeypatch.setattr("galleryvault.services.cold_archive.archive_one", fake_archive_fail)
    await run_cold_archive(session_factory=lambda: FakeSession(), task_manager=tm)

    data2 = list_notifications()
    assert data2["unread_count"] == 2
    kinds2 = [item["kind"] for item in reversed(data2["items"])]
    assert kinds2 == ["archive_start", "archive_fail"]


@pytest.mark.asyncio
async def test_archive_downloaded_gallery_notifications(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from galleryvault.app.state import app_state
    from galleryvault.services import download_worker
    from galleryvault.services.notifications import clear_notifications, list_notifications

    clear_notifications()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def execute(self, stmt):
            class Res:
                def scalar_one_or_none(self):
                    return "My Test Gallery"

            return Res()

    class FakeRepo:
        def __init__(self, session):
            pass

        async def update_archive_status(self, gid, status, error=None):
            pass

        async def count_active(self):
            return 0

    monkeypatch.setattr(download_worker, "DownloadRepository", FakeRepo)
    app_state.session_factory = lambda: FakeSession()
    app_state.settings = SimpleNamespace(
        telegram_notify_level="immediate",
        telegram_notify_lang="zh",
        telegram_bot_token=None,
    )

    # 1. Success outcome -> only archive_ok, no archive_start
    async def fake_archive_one_ok(gid, **kwargs):
        return tmp_path / "fake.cbz"

    monkeypatch.setattr("galleryvault.services.cold_archive.archive_one", fake_archive_one_ok)
    await download_worker._archive_downloaded_gallery(12345)

    data = list_notifications()
    assert data["unread_count"] == 1
    assert data["items"][0]["kind"] == "archive_ok"
    assert data["items"][0]["title"] == "My Test Gallery"

    # 2. Failure outcome -> only archive_fail, no archive_start
    clear_notifications()

    async def fake_archive_one_fail(gid, **kwargs):
        return None

    monkeypatch.setattr("galleryvault.services.cold_archive.archive_one", fake_archive_one_fail)
    await download_worker._archive_downloaded_gallery(12345)

    data2 = list_notifications()
    assert data2["unread_count"] == 1
    assert data2["items"][0]["kind"] == "archive_fail"
    assert data2["items"][0]["title"] == "My Test Gallery"


def test_comic_info_web_url_resolution(tmp_path: Path) -> None:
    from galleryvault.app.state import app_state
    from galleryvault.config import Settings

    source = tmp_path / "web-test"
    source.mkdir()
    (source / "01.jpg").write_bytes(b"image")
    cold_root = tmp_path / "cold"

    # 1. 跟随 settings 的 exhentai_base_url
    app_state.settings = Settings(exhentai_base_url="https://e-hentai.org/")
    dest1 = cold_pack_gallery(source=source, cold_root=cold_root, gid=1001, token="tok1", title="T1")
    with zipfile.ZipFile(dest1, "r") as zf:
        root1 = ElementTree.fromstring(zf.read("ComicInfo.xml"))
        assert root1.findtext("Web") == "https://e-hentai.org/g/1001/tok1/"

    # 2. 跟随 site 参数（覆盖全局下载源）
    app_state.settings = Settings(exhentai_base_url="https://exhentai.org")
    dest2 = cold_pack_gallery(source=source, cold_root=cold_root, gid=1002, token="tok2", title="T2", site="e-hentai")
    with zipfile.ZipFile(dest2, "r") as zf:
        root2 = ElementTree.fromstring(zf.read("ComicInfo.xml"))
        assert root2.findtext("Web") == "https://e-hentai.org/g/1002/tok2/"

    dest3 = cold_pack_gallery(source=source, cold_root=cold_root, gid=1003, token="tok3", title="T3", site="https://custom.e-hentai.org/")
    with zipfile.ZipFile(dest3, "r") as zf:
        root3 = ElementTree.fromstring(zf.read("ComicInfo.xml"))
        assert root3.findtext("Web") == "https://custom.e-hentai.org/g/1003/tok3/"

    # 3. 无 token 则可不写 Web
    dest4 = cold_pack_gallery(source=source, cold_root=cold_root, gid=1004, token=None, title="T4")
    with zipfile.ZipFile(dest4, "r") as zf:
        root4 = ElementTree.fromstring(zf.read("ComicInfo.xml"))
        assert root4.find("Web") is None

    # 4. 无 gid 则可不写 Web
    dest5 = cold_pack_gallery(source=source, cold_root=cold_root, gid=None, token="tok5", stable="1" * 64, title="T5")
    with zipfile.ZipFile(dest5, "r") as zf:
        root5 = ElementTree.fromstring(zf.read("ComicInfo.xml"))
        assert root5.find("Web") is None


@pytest.mark.asyncio
async def test_archive_one_clears_thumbs_when_pages_change(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from galleryvault.app.state import app_state
    from galleryvault.services.cold_archive import archive_one
    from galleryvault.services.thumbnails import ThumbnailService

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    ssd_root = tmp_path / "ssd"
    ssd_root.mkdir()
    thumb_root = tmp_path / "thumbs"
    thumb_root.mkdir()

    app_state.thumbnail_service = ThumbnailService(thumb_root)

    source = ssd_root / "301-Page Change Test"
    source.mkdir()
    # 归档后产生 2 页：0001.jpg, 0002.jpg
    (source / "01.jpg").write_bytes(b"p1")
    (source / "02.jpg").write_bytes(b"p2")

    # 创建该画廊已有的缩略图缓存目录及文件
    gallery_thumb_dir = thumb_root / "88"
    gallery_thumb_dir.mkdir(parents=True)
    (gallery_thumb_dir / "0.jpg").write_bytes(b"thumb0")

    gallery_obj = SimpleNamespace(
        id=88,
        gid=301,
        token="tok301",
        title="Page Change Test",
        storage_path=str(source),
        storage_type="folder",
        storage_size=10,
        file_size=10,
        trashed=False,
        path_hash="oldhash88",
        page_count=3,
        cover_path="01.jpg",
        source_meta=None,
    )

    # 模拟归档前 GalleryPage 有 3 页（01.jpg, 02.jpg, 03.jpg）
    old_rows = [("01.jpg",), ("02.jpg",), ("03.jpg",)]

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, model, ident):
            return gallery_obj if ident == 88 else None

        async def scalar(self, stmt):
            return None

        async def execute(self, stmt):
            class Res:
                def all(self):
                    if "gallery_pages" in str(stmt).lower():
                        return old_rows
                    return []

            return Res()

        def add_all(self, items):
            pass

        async def commit(self):
            pass

    dest = await archive_one(
        88,
        cold_root=cold_root,
        delete_source=False,
        session_factory=lambda: FakeSession(),
    )
    assert dest is not None
    # 由于归档前是 3 页（01.jpg, 02.jpg, 03.jpg），归档后是 2 页（0001.jpg, 0002.jpg），页变则清 thumbs！
    assert not gallery_thumb_dir.exists()


@pytest.mark.asyncio
async def test_archive_one_preserves_thumbs_when_pages_identical(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from galleryvault.app.state import app_state
    from galleryvault.services.cold_archive import archive_one
    from galleryvault.services.thumbnails import ThumbnailService

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    ssd_root = tmp_path / "ssd"
    ssd_root.mkdir()
    thumb_root = tmp_path / "thumbs"
    thumb_root.mkdir()

    app_state.thumbnail_service = ThumbnailService(thumb_root)

    source = ssd_root / "302-Page Same Test"
    source.mkdir()
    # 归档后产生 2 页：0001.jpg, 0002.jpg
    (source / "0001.jpg").write_bytes(b"p1")
    (source / "0002.jpg").write_bytes(b"p2")

    # 创建该画廊已有的缩略图缓存目录及文件
    gallery_thumb_dir = thumb_root / "89"
    gallery_thumb_dir.mkdir(parents=True)
    thumb_file = gallery_thumb_dir / "0.jpg"
    thumb_file.write_bytes(b"thumb0")

    gallery_obj = SimpleNamespace(
        id=89,
        gid=302,
        token="tok302",
        title="Page Same Test",
        storage_path=str(source),
        storage_type="folder",
        storage_size=10,
        file_size=10,
        trashed=False,
        path_hash="oldhash89",
        page_count=2,
        cover_path="0001.jpg",
        source_meta=None,
    )

    # 模拟归档前 GalleryPage 页数和文件名完全一致（0001.jpg, 0002.jpg）
    old_rows = [("0001.jpg",), ("0002.jpg",)]

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, model, ident):
            return gallery_obj if ident == 89 else None

        async def scalar(self, stmt):
            return None

        async def execute(self, stmt):
            class Res:
                def all(self):
                    if "gallery_pages" in str(stmt).lower():
                        return old_rows
                    return []

            return Res()

        def add_all(self, items):
            pass

        async def commit(self):
            pass

    dest = await archive_one(
        89,
        cold_root=cold_root,
        delete_source=False,
        session_factory=lambda: FakeSession(),
    )
    assert dest is not None
    # 页数与顺序完全一致则保留 thumbs
    assert gallery_thumb_dir.exists()
    assert thumb_file.exists()
    assert thumb_file.read_bytes() == b"thumb0"




