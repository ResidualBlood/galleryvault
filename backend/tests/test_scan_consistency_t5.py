"""Regression tests for T5 scan consistency fixes.

Covers:
- missing / empty scan root must not mark the library as expunged
- bare-directory name heuristic must not prune subtrees before a scanner matches
- ZIP member names written without the UTF-8 flag (GBK) are decoded correctly
- stale ZipFile cache entries are cleaned up
- thumbnails are written atomically and honor EXIF orientation
"""

from __future__ import annotations

import struct
import zipfile
import zlib
from io import BytesIO
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from galleryvault.app.state import app_state
from galleryvault.config import Settings
from galleryvault.scanners import archive as archive_module
from galleryvault.scanners.archive import CbzZipScanner, detect_zip_metadata_encoding
from galleryvault.scanners.base import ExistingGallery
from galleryvault.services import scan_worker, thumbnails
from galleryvault.services.library import LibraryService
from galleryvault.services.scan_worker import run_scan
from galleryvault.services.tasks import TaskManager
from galleryvault.services.thumbnails import ThumbnailService


def _jpeg(width: int = 40, height: int = 20, exif_orientation: int | None = None) -> bytes:
    image = Image.new("RGB", (width, height), "red")
    buffer = BytesIO()
    if exif_orientation is None:
        image.save(buffer, format="JPEG")
    else:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def _write_stored_zip(path: Path, entries: list[tuple[bytes, bytes]]) -> None:
    """Write a ZIP with raw member-name bytes and flag_bits=0 (no UTF-8 flag)."""
    local = b""
    central = b""
    offset = 0
    for raw_name, data in entries:
        crc = zlib.crc32(data) & 0xFFFFFFFF
        local_header = (
            struct.pack(
                "<4sHHHHHIIIHH",
                b"PK\x03\x04",
                20,
                0,
                0,
                0,
                0,
                crc,
                len(data),
                len(data),
                len(raw_name),
                0,
            )
            + raw_name
            + data
        )
        central += (
            struct.pack(
                "<4sHHHHHHIIIHHHHHII",
                b"PK\x01\x02",
                20,
                20,
                0,
                0,
                0,
                0,
                crc,
                len(data),
                len(data),
                len(raw_name),
                0,
                0,
                0,
                0,
                0,
                offset,
            )
            + raw_name
        )
        local += local_header
        offset += len(local_header)
    eocd = struct.pack(
        "<4sHHHHIIH", b"PK\x05\x06", 0, 0, len(entries), len(entries), len(central), len(local), 0
    )
    path.write_bytes(local + central + eocd)


# ---------------------------------------------------------------------------
# library: incomplete root detection
# ---------------------------------------------------------------------------


def test_missing_root_is_incomplete_and_yields_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "not-mounted"
    service = LibraryService([missing])

    assert list(service.candidates()) == []
    assert service.scan_incomplete is True
    assert str(missing) in service.incomplete_roots


def test_empty_existing_root_with_known_rows_is_incomplete(tmp_path: Path) -> None:
    empty = tmp_path / "library"
    empty.mkdir()
    known = {
        "hash": ExistingGallery(
            path=str(empty / "12345-gone"),
            signature="sig",
            gid=12345,
            gallery_id=1,
            storage_type="folder",
            title="Gone",
        )
    }
    service = LibraryService([empty], existing=known)

    assert list(service.candidates()) == []
    assert service.scan_incomplete is True


def test_empty_root_without_known_rows_stays_complete(tmp_path: Path) -> None:
    """An empty fresh root (e.g. downloads) must not disable expunge."""
    empty = tmp_path / "downloads"
    empty.mkdir()
    service = LibraryService([empty])

    assert list(service.candidates()) == []
    assert service.scan_incomplete is False


def test_root_with_gallery_is_complete(tmp_path: Path) -> None:
    gallery = tmp_path / "library" / "123-My Gallery"
    gallery.mkdir(parents=True)
    (gallery / "00000001.jpg").write_bytes(b"page")
    service = LibraryService([tmp_path / "library"])

    candidates = list(service.candidates())

    assert candidates
    assert service.scan_incomplete is False


@pytest.mark.asyncio
async def test_run_scan_skips_expunge_when_root_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance: a temporarily missing root must not expunge any rows."""
    orig_tm = app_state.task_manager
    orig_session = app_state.session_factory
    orig_settings = app_state.settings
    missing_root = str(tmp_path / "not-mounted")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def begin(self):
            return self

    class FakeRepo:
        expunge_calls: ClassVar[list[str]] = []
        find_missing_calls: ClassVar[list[object]] = []
        mark_calls: ClassVar[list[list[int]]] = []

        def __init__(self, session):
            pass

        async def fetch_existing_rows_raw(self, roots):
            return []

        async def fetch_starred_and_custom_tag_metadata(self):
            return set(), set(), set()

        @staticmethod
        def parse_existing_rows(
            raw_rows, roots, *, custom_tag_ids=None, fav_gids=None, local_list_ids=None
        ):
            return {}

        async def fetch_expunge_candidates(self):
            FakeRepo.expunge_calls.append("modern")
            return []

        async def expunge_missing(self, roots, seen_hashes):
            FakeRepo.expunge_calls.append("legacy")
            return 5

        @staticmethod
        def find_missing_ids(candidates, roots, seen):
            FakeRepo.find_missing_calls.append((list(candidates), list(roots), set(seen)))
            return [999]

        async def mark_expunged(self, ids):
            FakeRepo.mark_calls.append(list(ids))
            return len(ids)

        async def sync_duplicates(self, duplicates):
            pass

        async def metadata_map(self, gids):
            return {}

    class FakeIngest:
        def __init__(self, session):
            pass

        async def ingest(self, batch):
            pass

    try:
        tm = TaskManager()
        app_state.task_manager = tm
        app_state.session_factory = lambda: FakeSession()
        app_state.settings = Settings(
            library_roots=[missing_root],
            download_root="",
            cold_storage_root="",
            scan_batch_size=10,
            auto_sync_tags=False,
        )

        monkeypatch.setattr(scan_worker, "GalleryRepository", FakeRepo)
        monkeypatch.setattr(scan_worker, "GalleryIngestService", FakeIngest)
        monkeypatch.setattr(scan_worker, "backfill_image_quality", AsyncMock(return_value=0))
        monkeypatch.setattr(
            "galleryvault.services.series.rebuild_series_groups", AsyncMock(return_value={})
        )
        monkeypatch.setattr(
            "galleryvault.services.duplicates.scan_library_cross_gid_duplicates",
            AsyncMock(return_value=[]),
        )

        await run_scan()

        assert FakeRepo.expunge_calls == []
        assert FakeRepo.find_missing_calls == []
        assert FakeRepo.mark_calls == []
        assert tm.scan_state["last"]["expunged"] == 0
        assert tm.scan_state["scan_incomplete"] is True
        assert missing_root in tm.scan_state["incomplete_roots"]
    finally:
        app_state.task_manager = orig_tm
        app_state.session_factory = orig_session
        app_state.settings = orig_settings


# ---------------------------------------------------------------------------
# library: bare-directory heuristic must not prune subtrees
# ---------------------------------------------------------------------------


def test_bare_dir_name_without_scanner_does_not_prune_nested_gallery(tmp_path: Path) -> None:
    outer = tmp_path / "2023 - Trip"
    nested = outer / "55555-real-gallery"
    nested.mkdir(parents=True)
    (nested / ".ehviewer").write_text("VERSION2\n", encoding="utf-8")
    (nested / "00000001.jpg").write_bytes(b"page")

    candidates = [c[0] for c in LibraryService([tmp_path]).candidates()]

    assert nested in candidates
    assert outer not in candidates


# ---------------------------------------------------------------------------
# archive: legacy member name encoding + cache cleanup
# ---------------------------------------------------------------------------


def test_cbz_decodes_gbk_member_names(tmp_path: Path) -> None:
    cbz = tmp_path / "gbk.cbz"
    _write_stored_zip(cbz, [("中文.jpg".encode("gbk"), b"page-bytes")])

    assert detect_zip_metadata_encoding(cbz) == "gbk"

    scanner = CbzZipScanner()
    meta = scanner.scan(cbz)
    assert [page.name for page in meta.pages] == ["中文.jpg"]

    stream = scanner.open_page(meta, meta.pages[0])
    try:
        assert stream.read() == b"page-bytes"
    finally:
        stream.close()


def test_get_cached_zip_runs_stale_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cbz = tmp_path / "cached.cbz"
    with zipfile.ZipFile(cbz, "w") as archive:
        archive.writestr("0001.jpg", b"page")

    calls: list[float] = []
    monkeypatch.setattr(
        archive_module,
        "_cleanup_stale_zips",
        lambda ttl=300.0: calls.append(ttl) or 0,
    )
    try:
        archive_module._get_cached_zip(cbz)
        assert calls == [300.0]
    finally:
        archive_module._close_all_zips()


# ---------------------------------------------------------------------------
# thumbnails: atomic write + EXIF orientation
# ---------------------------------------------------------------------------


def test_thumbnail_write_is_atomic_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ThumbnailService(tmp_path / "thumbs")

    def _boom(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr(thumbnails.os, "replace", _boom)

    with pytest.raises(OSError):
        service.get_or_create(1, 0, _jpeg())

    assert service.cached(1, 0) is None
    gallery_dir = tmp_path / "thumbs" / "1"
    assert list(gallery_dir.iterdir()) == []


def test_thumbnail_applies_exif_orientation(tmp_path: Path) -> None:
    service = ThumbnailService(tmp_path / "thumbs")
    path = service.get_or_create(1, 0, _jpeg(40, 20, exif_orientation=6))

    with Image.open(path) as thumb:
        assert thumb.size == (20, 40)


def test_thumbnail_cache_hit_keeps_existing_file(tmp_path: Path) -> None:
    service = ThumbnailService(tmp_path / "thumbs")
    first = service.get_or_create(1, 0, _jpeg())
    mtime = first.stat().st_mtime_ns

    second = service.get_or_create(1, 0, _jpeg(10, 10))

    assert second == first
    assert second.stat().st_mtime_ns == mtime
