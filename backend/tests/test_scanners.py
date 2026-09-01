import zipfile
from pathlib import Path

import pytest

from galleryvault.scanners.archive import CbrRarScanner, CbzZipScanner
from galleryvault.scanners.ehviewer import EhviewerDirScanner, parse_spider_info
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
