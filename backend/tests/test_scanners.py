import json
import zipfile
from pathlib import Path

import pytest

from galleryvault.scanners import registry
from galleryvault.scanners.archive import CbrRarScanner, CbzZipScanner
from galleryvault.scanners.ehviewer import (
    BareImageDirScanner,
    EhviewerDirScanner,
    parse_spider_info,
)
from galleryvault.services.library import LibraryService

TEMP = (
    Path("/TEMP")
    if Path("/TEMP").exists()
    else Path("/library")
    if Path("/library").exists()
    else Path(__file__).parents[1] / "TEMP"
)


def test_real_ehviewer_samples() -> None:
    if not TEMP.is_dir():
        pytest.skip("no TEMP/library sample galleries available")
    scanner = EhviewerDirScanner()
    galleries = [scanner.scan(path) for path in TEMP.iterdir() if path.is_dir()]
    if not galleries:
        pytest.skip("no TEMP/library sample galleries available")
    assert sorted(len(g.pages) for g in galleries) == [15, 76]
    assert all(g.pages[0].index == 0 for g in galleries)
    assert {g.gid for g in galleries} == {560135, 3452635}
    by_gid = {gallery.gid: gallery for gallery in galleries}
    assert by_gid[560135].source_meta["start_page"] == 0
    assert by_gid[560135].source_meta["mode"] == 1
    assert by_gid[560135].source_meta["preview_pages"] == 1
    assert by_gid[560135].source_meta["preview_per_page"] == 15
    assert len(by_gid[560135].source_meta["p_tokens"]) == 15
    assert by_gid[3452635].source_meta["preview_per_page"] == 76


def test_version2_spider_info_fields_are_decoded() -> None:
    info = parse_spider_info("VERSION2\n0000000a\n123\ntoken\n1\n5\n20\n20\n0 first\n1 second\n")
    assert info.start_page == 10
    assert info.gid == 123
    assert info.mode == 1
    assert info.preview_pages == 5
    assert info.preview_per_page == 20
    assert info.pages == 20
    assert info.p_tokens == ["first", "second"]
    assert any("missing pToken" in warning for warning in info.warnings)


def test_version1_spider_info_is_supported() -> None:
    info = parse_spider_info("VERSION1\n0000000a\n123\ntoken\n1\n1\n1\n20\n0 first\n")
    assert info.version == "VERSION1"
    assert info.start_page == 10
    assert info.preview_per_page is None
    assert info.pages == 20


def test_version2_sort_mismatch_and_unicode(tmp_path: Path) -> None:
    path = tmp_path / "123-中文"
    path.mkdir()
    (path / ".ehviewer").write_text("VERSION2\n0\n123\ntoken\n1\n1\n2\n2\n0 x\n1 y\n")
    (path / "10.JPG").write_bytes(b"a")
    (path / "2.png").write_bytes(b"b")
    gallery = EhviewerDirScanner().scan(path)
    assert [p.name for p in gallery.pages] == ["2.png", "10.JPG"]
    (path / ".hidden.jpg").write_bytes(b"x")
    assert "page count mismatch" not in EhviewerDirScanner().scan(path).warnings
    (path / ".ehviewer").write_text("VERSION2\n0\n123\ntoken\n1\n1\n3\n3\n0 x\n1 y\n2 z\n")
    assert any(
        warning.startswith("page count mismatch")
        for warning in EhviewerDirScanner().scan(path).warnings
    )


def test_cbz_comicinfo_and_traversal(tmp_path: Path) -> None:
    good = tmp_path / "42-test.cbz"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("ComicInfo.xml", "<ComicInfo><Title>Example</Title></ComicInfo>")
        z.writestr("10.jpg", b"a")
        z.writestr("2.jpg", b"b")
    gallery = CbzZipScanner().scan(good)
    assert [p.name for p in gallery.pages] == ["2.jpg", "10.jpg"]
    assert gallery.source_meta["comic_info"]["Title"] == "Example"
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../escape.jpg", b"x")
    with pytest.raises(ValueError, match="unsafe"):
        CbzZipScanner().scan(bad)


def test_incremental_signature_detects_internal_change(tmp_path: Path) -> None:
    path = tmp_path / "1-test"
    path.mkdir()
    (path / ".ehviewer").write_text("VERSION2\n0\n1\nt\n1\n1\n1\n1\n0 x\n")
    image = path / "00000001.jpg"
    image.write_bytes(b"a")
    service = LibraryService([tmp_path])
    _, first = service.scan()
    _, second = service.scan()
    assert first.success == 1 and second.skipped == 1
    image.write_bytes(b"changed")
    _, third = service.scan()
    assert third.success == 1


def test_cbr_is_recognized_without_import_time_failure(tmp_path: Path) -> None:
    path = tmp_path / "book.cbr"
    path.write_bytes(b"not-rar")
    scanner = CbrRarScanner()
    assert scanner.matches(path)
    with pytest.raises((RuntimeError, ValueError)):
        scanner.scan(path)


def test_candidates_pruning_does_not_descend_into_gallery_subdirs(tmp_path: Path) -> None:
    """Candidates should yield gallery directories and archives without listing images."""
    gallery_dir = tmp_path / "123-My Gallery"
    gallery_dir.mkdir()
    (gallery_dir / "00000001.jpg").write_bytes(b"image 1")
    (gallery_dir / "00000002.jpg").write_bytes(b"image 2")

    nested_sub = tmp_path / "category" / "456-Nested Gallery"
    nested_sub.mkdir(parents=True)
    (nested_sub / ".ehviewer").write_text("VERSION2\n")
    (nested_sub / "00000001.jpg").write_bytes(b"image 1")

    archive_file = tmp_path / "category" / "789-archive.cbz"
    archive_file.write_bytes(b"dummy cbz")

    service = LibraryService([tmp_path])
    candidates = list(service.candidates())
    candidate_paths = [c[0] for c in candidates]

    assert gallery_dir in candidate_paths
    assert nested_sub in candidate_paths
    assert archive_file in candidate_paths
    # Images inside galleries must NOT be returned as candidates
    assert not any(p.suffix == ".jpg" for p in candidate_paths)


def test_cold_directory_without_ehviewer_is_scanned_and_readable(tmp_path: Path) -> None:
    """Cold storage directory without .ehviewer: scanned via .galleryvault.json + 0001.ext."""
    cold_dir = tmp_path / "12345"
    cold_dir.mkdir()
    (cold_dir / "0001.jpg").write_bytes(b"page 1 bytes")
    (cold_dir / "0002.png").write_bytes(b"page 2 bytes")
    (cold_dir / "ComicInfo.xml").write_text(
        "<ComicInfo><Title>Cold Title</Title><Writer>Cold Artist</Writer></ComicInfo>",
        encoding="utf-8",
    )
    gv_data = {
        "gid": 12345,
        "token": "a1b2c3d4",
        "tags": [
            {"namespace": "artist", "name": "Cold Artist"},
            {"namespace": "female", "name": "big breasts"},
        ],
        "p_tokens": ["ptok1", "ptok2"],
    }
    (cold_dir / ".galleryvault.json").write_text(json.dumps(gv_data), encoding="utf-8")

    scanner = registry.for_path(cold_dir)
    assert isinstance(scanner, BareImageDirScanner)
    meta = scanner.scan(cold_dir)

    assert meta.gid == 12345
    assert meta.token == "a1b2c3d4"
    assert meta.title == "Cold Title"
    assert meta.uploader == "Cold Artist"
    assert meta.storage_type == "folder"
    assert len(meta.pages) == 2
    assert [p.name for p in meta.pages] == ["0001.jpg", "0002.png"]
    assert meta.tags == [
        {"namespace": "artist", "name": "Cold Artist"},
        {"namespace": "female", "name": "big breasts"},
    ]

    # Verify flip-page / open_page works
    stream = scanner.open_page(meta, meta.pages[0])
    try:
        content = stream.read()
        assert content == b"page 1 bytes"
    finally:
        stream.close()


def test_cbz_scanner_reads_galleryvault_json_with_filename_gid_priority(tmp_path: Path) -> None:
    """CbzZipScanner reads .galleryvault.json to supplement gid/token/tags; filename gid has priority."""
    # Case 1: Filename has gid=999, but .galleryvault.json has gid=888 -> filename gid (999) wins
    cbz_with_gid = tmp_path / "999-my_safe_title.cbz"
    gv_payload = {
        "gid": 888,
        "token": "tok999",
        "tags": [{"namespace": "artist", "name": "ArtistA"}],
    }
    with zipfile.ZipFile(cbz_with_gid, "w") as z:
        z.writestr("0001.jpg", b"first page")
        z.writestr(".galleryvault.json", json.dumps(gv_payload))
        z.writestr("ComicInfo.xml", "<ComicInfo><Title>Zip Title</Title></ComicInfo>")

    scanner = registry.for_path(cbz_with_gid)
    assert isinstance(scanner, CbzZipScanner)
    meta = scanner.scan(cbz_with_gid)
    assert meta.gid == 999  # Filename gid has priority
    assert meta.token == "tok999"
    assert meta.tags == [{"namespace": "artist", "name": "ArtistA"}]
    assert meta.title == "Zip Title"

    # Case 2: Filename has NO gid (e.g. hash-title for ungid archive) -> gid supplemented from json
    cbz_ungid = tmp_path / "abcdef0123456789-ungid_title.cbz"
    gv_payload_2 = {
        "gid": 77777,
        "token": "tok777",
        "tags": [{"namespace": "misc", "name": "tag1"}],
    }
    with zipfile.ZipFile(cbz_ungid, "w") as z:
        z.writestr("0001.jpg", b"ungid first page")
        z.writestr(".galleryvault.json", json.dumps(gv_payload_2))

    meta2 = scanner.scan(cbz_ungid)
    assert meta2.gid == 77777  # Supplemented from .galleryvault.json
    assert meta2.token == "tok777"
    assert meta2.tags == [{"namespace": "misc", "name": "tag1"}]

    # Test open_page on CBZ
    stream = scanner.open_page(meta2, meta2.pages[0])
    try:
        assert stream.read() == b"ungid first page"
    finally:
        stream.close()


def test_library_candidates_includes_cold_directory_and_cbz(tmp_path: Path) -> None:
    """Library candidates traversal picks up both cold directory without .ehviewer and cold cbz."""
    cold_root = tmp_path / "cold"
    cold_root.mkdir()

    # Partitioned cold dir: {cold}/dir/ab/cd/12345/
    cold_dir = cold_root / "dir" / "ab" / "cd" / "12345"
    cold_dir.mkdir(parents=True)
    (cold_dir / "0001.jpg").write_bytes(b"p1")
    (cold_dir / ".galleryvault.json").write_text(json.dumps({"gid": 12345, "token": "t1"}))

    # Partitioned cold cbz: {cold}/cbz/ef/01/67890-title.cbz
    cold_cbz_parent = cold_root / "cbz" / "ef" / "01"
    cold_cbz_parent.mkdir(parents=True)
    cold_cbz = cold_cbz_parent / "67890-title.cbz"
    with zipfile.ZipFile(cold_cbz, "w") as z:
        z.writestr("0001.jpg", b"p1")
        z.writestr(".galleryvault.json", json.dumps({"gid": 67890, "token": "t2"}))

    service = LibraryService([cold_root])
    candidates = [c[0] for c in service.candidates()]

    assert cold_dir in candidates
    assert cold_cbz in candidates
    # Internal page images must not be yielded as separate candidates
    assert not any(p.suffix == ".jpg" for p in candidates)


def test_library_scan_batches_preserves_cold_gallery_metadata_and_pages(tmp_path: Path) -> None:
    """End-to-end: scan_batches picks up cold dir and cbz, preserving gid/token/tags and flippable pages."""
    cold_root = tmp_path / "cold"

    # Cold dir gallery
    cold_dir = cold_root / "dir" / "ab" / "cd" / "55555"
    cold_dir.mkdir(parents=True)
    (cold_dir / "0001.jpg").write_bytes(b"cold dir page 1")
    (cold_dir / "0002.jpg").write_bytes(b"cold dir page 2")
    (cold_dir / "ComicInfo.xml").write_text("<ComicInfo><Title>Dir Title</Title></ComicInfo>", encoding="utf-8")
    (cold_dir / ".galleryvault.json").write_text(
        json.dumps({
            "gid": 55555,
            "token": "dir_token",
            "tags": [{"namespace": "artist", "name": "DirArtist"}],
        }),
        encoding="utf-8",
    )

    # Cold cbz gallery
    cold_cbz_parent = cold_root / "cbz" / "12" / "34"
    cold_cbz_parent.mkdir(parents=True)
    cold_cbz = cold_cbz_parent / "66666-CbzTitle.cbz"
    with zipfile.ZipFile(cold_cbz, "w") as z:
        z.writestr("0001.png", b"cold cbz page 1")
        z.writestr("ComicInfo.xml", "<ComicInfo><Title>Cbz Title</Title></ComicInfo>")
        z.writestr(
            ".galleryvault.json",
            json.dumps({
                "gid": 66666,
                "token": "cbz_token",
                "tags": [{"namespace": "character", "name": "CbzHero"}],
            }),
        )

    service = LibraryService([cold_root])
    batches = list(service.scan_batches())
    all_galleries = [g for b in batches for g in b]

    by_gid = {g.gid: g for g in all_galleries}
    assert 55555 in by_gid
    assert 66666 in by_gid

    dir_g = by_gid[55555]
    assert dir_g.token == "dir_token"
    assert dir_g.tags == [{"namespace": "artist", "name": "DirArtist"}]
    assert dir_g.title == "Dir Title"
    assert len(dir_g.pages) == 2

    # Verify flip-page for dir gallery
    scanner_dir = registry.for_path(dir_g.path)
    assert scanner_dir is not None
    with scanner_dir.open_page(dir_g, dir_g.pages[0]) as stream:
        assert stream.read() == b"cold dir page 1"

    cbz_g = by_gid[66666]
    assert cbz_g.token == "cbz_token"
    assert cbz_g.tags == [{"namespace": "character", "name": "CbzHero"}]
    assert cbz_g.title == "Cbz Title"
    assert len(cbz_g.pages) == 1

    # Verify flip-page for cbz gallery
    scanner_cbz = registry.for_path(cbz_g.path)
    assert scanner_cbz is not None
    with scanner_cbz.open_page(cbz_g, cbz_g.pages[0]) as stream:
        assert stream.read() == b"cold cbz page 1"
