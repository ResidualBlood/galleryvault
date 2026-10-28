"""S2: unreadable archives are reported once and repairing them retries.

Covers the remaining half of 05 P3-2: a broken/corrupt archive used to be
re-parsed and re-reported on every scan.  The scan loop now keeps a
process-wide ``(path_hash, signature)`` cache of failed files, so the parse,
the error log and the error counter happen once; replacing the file changes
its signature and the next scan retries.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import ClassVar

import pytest

from galleryvault.services import library as library_module
from galleryvault.services.library import LibraryService, reset_known_bad_files


@pytest.fixture(autouse=True)
def _clear_known_bad_cache():
    reset_known_bad_files()
    yield
    reset_known_bad_files()


def _write_broken_archive(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a zip file")
    return path


def _write_valid_archive(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("00000001.jpg", b"page-bytes")
    return path


def _scan_errors(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_broken_archive_error_reported_once_per_process(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    broken = _write_broken_archive(tmp_path / "lib" / "broken.cbz")
    caplog.set_level(logging.DEBUG)

    first = LibraryService([broken.parent])
    assert list(first.scan_batches()) == []
    assert first.last_counters.errors == 1
    assert len(_scan_errors(caplog)) == 1

    caplog.clear()
    # A brand new service (i.e. the next scheduled scan) must not re-parse or
    # re-report the same unreadable file.
    second = LibraryService([broken.parent])
    assert list(second.scan_batches()) == []
    assert second.last_counters.errors == 0
    assert second.last_counters.skipped == 1
    assert _scan_errors(caplog) == []
    assert any("skip known bad file" in record.getMessage() for record in caplog.records)


def test_repaired_archive_with_new_signature_is_retried(tmp_path: Path) -> None:
    broken = _write_broken_archive(tmp_path / "lib" / "fixme.cbz")

    first = LibraryService([broken.parent])
    list(first.scan_batches())
    assert first.last_counters.errors == 1

    # Repair in place: size/mtime change, so the signature differs and the
    # cached failure must not be reused.
    _write_valid_archive(broken)

    second = LibraryService([broken.parent])
    batches = list(second.scan_batches())

    assert second.last_counters.errors == 0
    assert len(batches) == 1
    assert [page.name for page in batches[0][0].pages] == ["00000001.jpg"]
    assert broken.resolve() in {gallery.path for gallery in batches[0]}
    # The stale failure entry was dropped once the file parsed again.
    assert library_module._KNOWN_BAD_FILES == {}


def test_each_broken_archive_is_reported_once(tmp_path: Path) -> None:
    _write_broken_archive(tmp_path / "lib" / "a.cbz")
    _write_broken_archive(tmp_path / "lib" / "b.cbz")

    first = LibraryService([tmp_path / "lib"])
    list(first.scan_batches())
    assert first.last_counters.errors == 2

    second = LibraryService([tmp_path / "lib"])
    list(second.scan_batches())
    assert second.last_counters.errors == 0
    assert second.last_counters.skipped == 2


class _FlakyDirScanner:
    """Directory scanner that fails once and then works (transient IO)."""

    storage_type = "folder"
    calls: ClassVar[int] = 0

    def fingerprint(self, path: Path) -> str:
        return "fixed-signature"

    def scan(self, path: Path):
        raise OSError("transient read error")


def test_transient_directory_failure_is_not_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gallery = tmp_path / "lib" / "123456-transient"
    gallery.mkdir(parents=True)
    (gallery / ".ehviewer").write_text("VERSION2\n", encoding="utf-8")

    scanner = _FlakyDirScanner()
    monkeypatch.setattr(
        library_module.registry,
        "for_path",
        lambda path: scanner if Path(path).resolve() == gallery.resolve() else None,
    )

    for _ in range(2):
        service = LibraryService([tmp_path / "lib"])
        list(service.scan_batches())
        assert service.last_counters.errors == 1, "directory failures must stay retryable"


def test_known_bad_cache_is_bounded() -> None:
    for index in range(library_module._KNOWN_BAD_LIMIT + 25):
        library_module._remember_bad_file(f"hash-{index}", "sig")

    assert len(library_module._KNOWN_BAD_FILES) == library_module._KNOWN_BAD_LIMIT
    # Oldest entries are evicted first, so the newest failure is still cached.
    newest = (f"hash-{library_module._KNOWN_BAD_LIMIT + 24}", "sig")
    assert newest in library_module._KNOWN_BAD_FILES
