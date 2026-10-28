"""Regression tests for worktree B1-F2: library consistency and media caches."""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

import pytest

from galleryvault.metadata.sidecar import (
    SIDECAR_FILENAME,
    parse_galleryvault_json,
    read_galleryvault_json,
    write_galleryvault_json,
)
from galleryvault.scanners.base import ExistingGallery
from galleryvault.scanners.ehviewer import EhviewerDirScanner
from galleryvault.services import storage_usage
from galleryvault.services.library import LibraryService, _root_priority
from galleryvault.services.storage_usage import measure_dir_bytes
from galleryvault.services.thumbnails import ThumbnailService


def _make_ehviewer_dir(path: Path, pages: int = 2) -> Path:
    path.mkdir(parents=True)
    (path / ".ehviewer").write_text("VERSION2\n0\n1\nt\n1\n1\n1\n1\n0 x\n")
    for index in range(1, pages + 1):
        (path / f"{index:08d}.jpg").write_bytes(b"x" * 10)
    return path


def _existing(path: Path, signature: str, gid: int = 100) -> dict[str, ExistingGallery]:
    key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
    return {
        key: ExistingGallery(
            path=str(path),
            signature=signature,
            gid=gid,
            gallery_id=1,
            storage_type="ehviewer_dir",
            title="t",
        )
    }


# ---------------------------------------------------------------------------
# 05 P2-6: directory signature must notice in-place page edits
# ---------------------------------------------------------------------------


def test_directory_signature_changes_when_page_rewritten(tmp_path: Path) -> None:
    gallery_dir = _make_ehviewer_dir(tmp_path / "100-gallery")
    galleries, _ = LibraryService([tmp_path]).scan()
    assert len(galleries) == 1
    first_signature = galleries[0].storage_signature

    # Rewrite a page without touching the directory entry or mtime.
    (gallery_dir / "00000001.jpg").write_bytes(b"y" * 25)

    service = LibraryService([tmp_path], existing=_existing(gallery_dir, first_signature))
    rescanned, counters = service.scan()

    assert counters.skipped == 0
    assert len(rescanned) == 1
    assert rescanned[0].storage_signature != first_signature


def test_legacy_scanner_signature_still_skips(tmp_path: Path) -> None:
    """Rows written before the page-stat digest existed keep skipping."""
    gallery_dir = _make_ehviewer_dir(tmp_path / "100-gallery")
    legacy = EhviewerDirScanner().fingerprint(gallery_dir)

    _, counters = LibraryService([tmp_path], existing=_existing(gallery_dir, legacy)).scan()

    assert counters.skipped == 1


# ---------------------------------------------------------------------------
# 05 P3-5: root priority must compare resolved roots
# ---------------------------------------------------------------------------


def test_root_priority_resolves_symlinked_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    gallery_dir = real / "1-gallery"
    gallery_dir.mkdir()

    assert _root_priority([link], gallery_dir) == 0


# ---------------------------------------------------------------------------
# 05 P2-13: symlinked files pointing outside the root are not candidates
# ---------------------------------------------------------------------------


def test_candidates_skip_symlink_archive_outside_root(tmp_path: Path) -> None:
    library = tmp_path / "lib"
    library.mkdir()
    outside = tmp_path / "outside.cbz"
    outside.write_bytes(b"PK")
    inside = library / "inside.cbz"
    inside.write_bytes(b"PK")
    (library / "link.cbz").symlink_to(outside)

    paths = [path for path, _priority in LibraryService([library]).candidates()]

    assert inside in paths
    assert (library / "link.cbz") not in paths


def test_candidates_keep_symlink_archive_inside_root(tmp_path: Path) -> None:
    library = tmp_path / "lib"
    target = library / "real.cbz"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"PK")
    (library / "link.cbz").symlink_to(target)

    paths = [path for path, _priority in LibraryService([library]).candidates()]

    assert (library / "link.cbz") in paths


# ---------------------------------------------------------------------------
# 05 P3-13: scan roots are normalized before dedupe
# ---------------------------------------------------------------------------


def test_scan_roots_dedupes_trailing_slash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.state import app_state
    from galleryvault.config import Settings
    from galleryvault.services.scan_worker import _scan_roots

    library = tmp_path / "library"
    library.mkdir()
    settings = Settings(
        library_roots=[str(library), f"{library}/"],
        download_root=str(library),
        archive_roots=[],
    )
    monkeypatch.setattr(app_state, "settings", settings)

    roots = _scan_roots()

    assert roots == [str(library.resolve())]


# ---------------------------------------------------------------------------
# 05 P3-6: a failed gdata round stops the backfill instead of skipping rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_stops_after_gdata_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.state import app_state
    from galleryvault.services import scan_worker

    class Row:
        def __init__(self, index: int) -> None:
            self.id = index
            self.gid = 1000 + index
            self.token = "abcdef1234"
            self.storage_size = 10
            self.storage_type = "folder"

    rows = [Row(index) for index in range(200)]

    class FakeRepo:
        def __init__(self, session: object) -> None:
            pass

        async def pending_image_quality_gids(self, limit: int, last_id: int):
            return rows

        async def metadata_map(self, gids: list[int]):
            return {}

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc: object) -> None:
            return None

    def session_factory() -> FakeSession:
        return FakeSession()

    calls = {"refresh": 0}

    async def failing_refresh(*args: object, **kwargs: object):
        calls["refresh"] += 1
        raise RuntimeError("gdata down")

    monkeypatch.setattr(app_state, "eh_client", object())
    monkeypatch.setattr(scan_worker, "_get_background_session_factory", lambda: session_factory)
    monkeypatch.setattr(scan_worker, "GalleryRepository", FakeRepo)
    monkeypatch.setattr(scan_worker, "refresh_gdata", failing_refresh)
    monkeypatch.setattr(scan_worker.asyncio, "sleep", _no_sleep)

    processed = await asyncio.wait_for(scan_worker.backfill_image_quality(), timeout=5)

    assert processed == 0
    assert calls["refresh"] == 1


async def _no_sleep(_seconds: float) -> None:
    return None


# ---------------------------------------------------------------------------
# 05 P2-9: zero-byte placeholders must not count as cached thumbnails
# ---------------------------------------------------------------------------


def test_zero_byte_placeholder_is_reported_missing(tmp_path: Path) -> None:
    service = ThumbnailService(tmp_path)
    placeholder = service.cache_path(7, 0)
    placeholder.parent.mkdir(parents=True)
    placeholder.touch()

    assert service.has_missing_pages(7, 1) is True

    placeholder.write_bytes(b"jpeg")
    assert service.has_missing_pages(7, 1) is False


# ---------------------------------------------------------------------------
# 05 P2-10: duplicate-copy thumbnail dirs are pruned
# ---------------------------------------------------------------------------


def test_prune_dup_cache_removes_stale_keys(tmp_path: Path) -> None:
    service = ThumbnailService(tmp_path)
    keep = tmp_path / "dup" / "keep" / "0.jpg"
    keep.parent.mkdir(parents=True)
    keep.write_bytes(b"jpeg")
    stale = tmp_path / "dup" / "stale" / "0.jpg"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"jpeg" * 10)

    removed = service.prune_dup_cache({"keep"})

    assert removed == 1
    assert keep.is_file()
    assert not stale.parent.exists()


# ---------------------------------------------------------------------------
# 05 P2-11: sidecar writes are atomic
# ---------------------------------------------------------------------------


def test_sidecar_write_keeps_original_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "gallery"
    target.mkdir()
    write_galleryvault_json(target, gid=1, token="abcdef1234", title="T")
    original = (target / SIDECAR_FILENAME).read_bytes()

    def failing_replace(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("galleryvault.metadata.sidecar.os.replace", failing_replace)

    with pytest.raises(OSError):
        write_galleryvault_json(target, gid=2, title="X")

    assert (target / SIDECAR_FILENAME).read_bytes() == original
    assert sorted(path.name for path in target.iterdir()) == [SIDECAR_FILENAME]
    assert read_galleryvault_json(target)["title"] == "T"


# ---------------------------------------------------------------------------
# 02 P3-7: sidecar gid/token validation
# ---------------------------------------------------------------------------


def test_parse_sidecar_rejects_invalid_gid_and_token() -> None:
    parsed = parse_galleryvault_json({"gid": 0, "token": "../../etc/passwd"})
    assert parsed["gid"] is None
    assert parsed["token"] is None

    assert parse_galleryvault_json({"gid": -5})["gid"] is None

    valid = parse_galleryvault_json({"gid": 123, "token": "abcdef1234"})
    assert valid["gid"] == 123
    assert valid["token"] == "abcdef1234"


# ---------------------------------------------------------------------------
# 05 P3-7 / P3-8: storage measurement dedupes hard links and caps du output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_measure_dir_bytes_counts_hardlinks_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(storage_usage.shutil, "which", lambda _name: None)
    first = tmp_path / "a.bin"
    first.write_bytes(b"x" * 100)
    os.link(first, tmp_path / "b.bin")

    assert await measure_dir_bytes(tmp_path) == 100


@pytest.mark.asyncio
async def test_read_capped_reports_truncation() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"a" * 100)
    reader.feed_eof()

    data, truncated = await storage_usage._read_capped(reader, 10)

    assert truncated is True
    assert len(data) >= 10


# ---------------------------------------------------------------------------
# 05 P2-12: repair script keeps path_hash / duplicate records in sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_rename_updates_duplicate_records(tmp_path: Path) -> None:
    from galleryvault.db.models import DuplicateRecord
    from galleryvault.db.repositories.base import path_hash
    from galleryvault.scripts.repair_cold_archives import (
        update_duplicate_records_for_rename,
    )

    old_path = str(tmp_path / "100-old.cbz")
    new_path = str(tmp_path / "100-new.cbz")
    record = DuplicateRecord(
        gid=100,
        copies=[{"path": old_path, "key": path_hash(Path(old_path))}],
        winner_path=old_path,
    )

    changed = await update_duplicate_records_for_rename(
        None, old_path, new_path, [record]  # type: ignore[arg-type]
    )

    assert changed == 1
    assert record.winner_path == new_path
    assert record.copies[0]["path"] == new_path
    assert record.copies[0]["key"] == path_hash(Path(new_path))
