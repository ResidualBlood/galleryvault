"""Batch 1 scanner fixes (review 05: P2-1, P2-3, P2-4, P3-1, P3-2, P3-3, P3-4, P3-14)."""

import json
import typing
import zipfile
from pathlib import Path

import pytest

from galleryvault.scanners import sevenzip as sevenzip_mod
from galleryvault.scanners.archive import CbzZipScanner
from galleryvault.scanners.base import GalleryMeta
from galleryvault.scanners.ehviewer import (
    BareImageDirScanner,
    EhviewerDirScanner,
    JhentaiDirScanner,
    parse_gid_prefix,
)
from galleryvault.scanners.sevenzip import SevenZipScanner


def _write_zip(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)


# ---------------------------------------------------------------------------
# P2-1: ComicInfo.xml size cap
# ---------------------------------------------------------------------------


def test_cbz_oversize_comicinfo_is_skipped_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import galleryvault.scanners.archive as archive_mod

    cbz = tmp_path / "1-test.cbz"
    _write_zip(
        cbz,
        [
            ("0001.jpg", b"page"),
            ("ComicInfo.xml", b"<ComicInfo><Title>Too long to read</Title></ComicInfo>"),
        ],
    )
    monkeypatch.setattr(archive_mod, "MAX_COMICINFO_SIZE", 8)
    meta = CbzZipScanner().scan(cbz)
    assert [p.name for p in meta.pages] == ["0001.jpg"]
    assert "comic_info" not in meta.source_meta
    assert any("size limit" in warning for warning in meta.warnings)


# ---------------------------------------------------------------------------
# P2-3 / P2-4: 7z page count/order preserved, no full extraction for sizes
# ---------------------------------------------------------------------------


def test_sevenzip_scan_keeps_oversize_page_without_extracting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    py7zr = pytest.importorskip("py7zr")
    (tmp_path / "1.jpg").write_bytes(b"a" * 10)
    (tmp_path / "2.jpg").write_bytes(b"b" * 200)
    (tmp_path / "3.jpg").write_bytes(b"c" * 10)
    archive_path = tmp_path / "three-pages.7z"
    with py7zr.SevenZipFile(archive_path, "w") as archive:
        for name in ("1.jpg", "2.jpg", "3.jpg"):
            archive.write(tmp_path / name, name)

    def forbid_extract(*_args, **_kwargs):
        raise AssertionError("scan() must not decompress members to measure size")

    monkeypatch.setattr(sevenzip_mod, "MAX_ARCHIVE_PAGE_SIZE", 150)
    monkeypatch.setattr(py7zr.SevenZipFile, "extract", forbid_extract)

    meta = SevenZipScanner().scan(archive_path)
    assert [p.name for p in meta.pages] == ["1.jpg", "2.jpg", "3.jpg"]
    assert meta.file_count == 3
    assert [p.size for p in meta.pages] == [10, None, 10]
    assert any("exceed" in warning for warning in meta.warnings)


def test_sevenzip_scan_keeps_pages_when_sizes_are_unmeasurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    py7zr = pytest.importorskip("py7zr")
    (tmp_path / "1.jpg").write_bytes(b"a" * 10)
    (tmp_path / "2.jpg").write_bytes(b"b" * 10)
    archive_path = tmp_path / "no-sizes.7z"
    with py7zr.SevenZipFile(archive_path, "w") as archive:
        archive.write(tmp_path / "1.jpg", "1.jpg")
        archive.write(tmp_path / "2.jpg", "2.jpg")

    def forbid_extract(*_args, **_kwargs):
        raise AssertionError("scan() must not decompress members to measure size")

    monkeypatch.setattr(py7zr.SevenZipFile, "list", lambda self: [])
    monkeypatch.setattr(py7zr.SevenZipFile, "extract", forbid_extract)

    meta = SevenZipScanner().scan(archive_path)
    assert [p.name for p in meta.pages] == ["1.jpg", "2.jpg"]
    assert all(page.size is None for page in meta.pages)
    assert any("no measurable size" in warning for warning in meta.warnings)


def test_sevenzip_scan_annotation_is_gallery_meta() -> None:
    assert typing.get_type_hints(SevenZipScanner.scan)["return"] is GalleryMeta


# ---------------------------------------------------------------------------
# P3-1: page-less archives are rejected instead of being ingested
# ---------------------------------------------------------------------------


def test_cbz_without_images_is_rejected(tmp_path: Path) -> None:
    cbz = tmp_path / "empty.cbz"
    _write_zip(cbz, [("readme.txt", b"no pages here")])
    with pytest.raises(ValueError, match="no image pages"):
        CbzZipScanner().scan(cbz)


def test_sevenzip_without_images_is_rejected(tmp_path: Path) -> None:
    py7zr = pytest.importorskip("py7zr")
    (tmp_path / "payload.bin").write_bytes(b"not an image")
    archive_path = tmp_path / "empty.7z"
    with py7zr.SevenZipFile(archive_path, "w") as archive:
        archive.write(tmp_path / "payload.bin", "payload.bin")
    with pytest.raises(ValueError, match="no image pages"):
        SevenZipScanner().scan(archive_path)


# ---------------------------------------------------------------------------
# P3-2: encrypted members must warn, not abort the scan on every run
# ---------------------------------------------------------------------------


def test_cbz_encrypted_comicinfo_and_sidecar_become_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cbz = tmp_path / "1-encrypted.cbz"
    _write_zip(
        cbz,
        [
            ("0001.jpg", b"page"),
            ("ComicInfo.xml", b"<ComicInfo><Title>T</Title></ComicInfo>"),
            (".galleryvault.json", json.dumps({"gid": 12345, "token": "tok"})),
        ],
    )
    orig_read = zipfile.ZipFile.read

    def fake_read(self, name, pwd=None):
        if name in {"ComicInfo.xml", ".galleryvault.json"}:
            raise RuntimeError(f"File {name} is encrypted, password required")
        return orig_read(self, name, pwd)

    monkeypatch.setattr(zipfile.ZipFile, "read", fake_read)
    meta = CbzZipScanner().scan(cbz)
    assert [p.name for p in meta.pages] == ["0001.jpg"]
    assert any("cannot read ComicInfo.xml" in warning for warning in meta.warnings)
    assert any("cannot read .galleryvault.json" in warning for warning in meta.warnings)


# ---------------------------------------------------------------------------
# P3-3: JHenTai probe is not limited to the first 4 KiB
# ---------------------------------------------------------------------------


def test_jhentai_metadata_gallery_key_after_4kb(tmp_path: Path) -> None:
    gallery_dir = tmp_path / "123456 - Long Title"
    gallery_dir.mkdir()
    (gallery_dir / "1.jpg").write_bytes(b"page")
    payload = {
        "pad": "x" * 6000,
        "gallery": {"gid": 123456, "token": "tok", "title": "Long Title", "pageCount": 1},
        "images": ["1.jpg"],
    }
    raw = json.dumps(payload).encode("utf-8")
    assert raw.index(b'"gallery"') > 4096
    (gallery_dir / "metadata").write_bytes(raw)

    scanner = JhentaiDirScanner()
    assert scanner.matches(gallery_dir) is True
    meta = scanner.scan(gallery_dir)
    assert meta.gid == 123456
    assert [p.name for p in meta.pages] == ["1.jpg"]


def test_jhentai_metadata_without_gallery_key_does_not_match(tmp_path: Path) -> None:
    gallery_dir = tmp_path / "123456 - Not JHenTai"
    gallery_dir.mkdir()
    (gallery_dir / "1.jpg").write_bytes(b"page")
    (gallery_dir / "metadata").write_text(json.dumps({"title": "x"}), encoding="utf-8")
    assert JhentaiDirScanner().matches(gallery_dir) is False


# ---------------------------------------------------------------------------
# P3-4: one gid rule for archive names and directory names
# ---------------------------------------------------------------------------


def test_gid_prefix_rule_shared_between_archives_and_directories(tmp_path: Path) -> None:
    assert parse_gid_prefix("12345-title") == 12345
    assert parse_gid_prefix("12345 - title") == 12345
    assert parse_gid_prefix("1234-title") is None

    short_archive = tmp_path / "1234-short.cbz"
    _write_zip(short_archive, [("0001.jpg", b"page")])
    long_archive = tmp_path / "12345-long.cbz"
    _write_zip(long_archive, [("0001.jpg", b"page")])
    assert CbzZipScanner().scan(short_archive).gid is None
    assert CbzZipScanner().scan(long_archive).gid == 12345

    short_dir = tmp_path / "1234 - misc"
    short_dir.mkdir()
    (short_dir / "0001.jpg").write_bytes(b"page")
    long_dir = tmp_path / "12345 - real"
    long_dir.mkdir()
    (long_dir / "0001.jpg").write_bytes(b"page")
    bare = BareImageDirScanner()
    assert bare.matches(short_dir) is True
    assert bare.scan(short_dir).gid is None
    assert bare.scan(long_dir).gid == 12345

    # A directory with an .ehviewer sentinel keeps trusting its parsed metadata
    # even when the name has a short numeric prefix.
    sentinel_dir = tmp_path / "1234-sentinel"
    sentinel_dir.mkdir()
    (sentinel_dir / ".ehviewer").write_text(
        "VERSION1\n0\n1234\ntok\n1\n1\n1\n1\n0 pt\n", encoding="utf-8"
    )
    (sentinel_dir / "0001.jpg").write_bytes(b"page")
    assert EhviewerDirScanner().scan(sentinel_dir).gid == 1234
