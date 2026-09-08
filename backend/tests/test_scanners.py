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
    strip_gid_prefix,
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
    assert meta.title_jpn is None
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


def test_bare_image_dir_scanner_title_jpn_handling(tmp_path: Path) -> None:
    # 1. gid-日文 directory retains japanese title
    jpn_dir = tmp_path / "12345-日本語タイトル"
    jpn_dir.mkdir()
    (jpn_dir / "0001.jpg").write_bytes(b"p1")
    scanner = registry.for_path(jpn_dir)
    assert isinstance(scanner, BareImageDirScanner)
    meta = scanner.scan(jpn_dir)
    assert meta.gid == 12345
    assert meta.title_jpn == "日本語タイトル"

    # 2. Pure digit rest or pure digit title_jpn in json is dropped
    digit_dir = tmp_path / "67890"
    digit_dir.mkdir()
    (digit_dir / "0001.jpg").write_bytes(b"p1")
    (digit_dir / ".galleryvault.json").write_text(
        json.dumps({"gid": 67890, "title": "Real Title", "title_jpn": "67890"}),
        encoding="utf-8",
    )
    meta2 = scanner.scan(digit_dir)
    assert meta2.gid == 67890
    assert meta2.title == "Real Title"
    assert meta2.title_jpn is None


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


def test_cbz_scanner_open_page_consecutive_reads(tmp_path: Path) -> None:
    cbz_file = tmp_path / "consecutive.cbz"
    with zipfile.ZipFile(cbz_file, "w") as z:
        z.writestr("0001.jpg", b"page-1-bytes")
        z.writestr("0002.jpg", b"page-2-bytes")

    scanner = CbzZipScanner()
    meta = scanner.scan(cbz_file)

    # First open_page call
    with scanner.open_page(meta, meta.pages[0]) as s1:
        assert s1.read() == b"page-1-bytes"

    # Second open_page call on same CBZ
    with scanner.open_page(meta, meta.pages[1]) as s2:
        assert s2.read() == b"page-2-bytes"

    # Third open_page call on first page again (reusing cached ZipFile)
    with scanner.open_page(meta, meta.pages[0]) as s3:
        assert s3.read() == b"page-1-bytes"


def test_strip_gid_prefix() -> None:
    assert strip_gid_prefix("2849972-[雨 と 棘] 漫画", 2849972) == "[雨 と 棘] 漫画"
    assert strip_gid_prefix("2849972-2849972-[雨 と 棘] 漫画", 2849972) == "[雨 と 棘] 漫画"
    assert strip_gid_prefix("2849972_Title", 2849972) == "Title"
    assert strip_gid_prefix("2849972 Title", 2849972) == "Title"
    assert strip_gid_prefix("2849972", 2849972) == ""
    assert strip_gid_prefix("12345-Title", None) == "Title"
    assert strip_gid_prefix("1984-A Novel", 999999) == "1984-A Novel"
    assert strip_gid_prefix("1984-A Novel", None) == "A Novel"
    assert strip_gid_prefix("", 123) == ""
    assert strip_gid_prefix("Plain Title", 123) == "Plain Title"


def test_scanners_strip_gid_prefix_on_fallback(tmp_path: Path) -> None:
    # 1. EhviewerDirScanner with directory name 12345-CleanTitle
    eh_dir = tmp_path / "12345-CleanTitle"
    eh_dir.mkdir()
    (eh_dir / ".ehviewer").write_text("VERSION1\n0\n12345\ntoken\n1\n1\n1\n1\n0 pt\n")
    (eh_dir / "0001.jpg").write_bytes(b"page")
    eh_meta = EhviewerDirScanner().scan(eh_dir)
    assert eh_meta.title == "CleanTitle"

    # 2. BareImageDirScanner with double GID in directory name
    bare_dir = tmp_path / "12345-12345-BareTitle"
    bare_dir.mkdir()
    (bare_dir / "0001.jpg").write_bytes(b"page")
    bare_meta = BareImageDirScanner().scan(bare_dir)
    assert bare_meta.title == "BareTitle"

    # 3. CbzZipScanner with GID prefix in filename
    cbz_path = tmp_path / "12345-ArchiveTitle.cbz"
    with zipfile.ZipFile(cbz_path, "w") as z:
        z.writestr("0001.jpg", b"page")
    archive_meta = CbzZipScanner().scan(cbz_path)
    assert archive_meta.title == "ArchiveTitle"


def test_cbz_comic_info_writer_truncation(tmp_path: Path) -> None:
    cbz_path = tmp_path / "long_writer.cbz"
    long_writer = "A" * 200
    with zipfile.ZipFile(cbz_path, "w") as z:
        z.writestr("0001.jpg", b"page")
        z.writestr(
            "ComicInfo.xml",
            f"<ComicInfo><Title>T</Title><Writer>{long_writer}</Writer></ComicInfo>".encode(),
        )
    archive_meta = CbzZipScanner().scan(cbz_path)
    assert len(archive_meta.uploader) == 128
    assert archive_meta.uploader == "A" * 128


def test_ehviewer_comic_info_writer_truncation(tmp_path: Path) -> None:
    bare_dir = tmp_path / "12345-LongWriter"
    bare_dir.mkdir()
    (bare_dir / "0001.jpg").write_bytes(b"page")
    long_writer = "B" * 200
    (bare_dir / "ComicInfo.xml").write_text(
        f"<ComicInfo><Title>T</Title><Writer>{long_writer}</Writer></ComicInfo>",
        encoding="utf-8",
    )
    meta = BareImageDirScanner().scan(bare_dir)
    assert meta.uploader is not None
    assert len(meta.uploader) == 128
    assert meta.uploader == "B" * 128


def test_get_scan_roots_includes_archive_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from galleryvault.app.dependencies import get_scan_roots
    from galleryvault.app.state import app_state
    from galleryvault.config import Settings

    custom_settings = Settings(
        library_roots=[str(tmp_path / "lib")],
        download_root=str(tmp_path / "dl"),
        archive_roots=[str(tmp_path / "archive1"), str(tmp_path / "archive2")],
    )
    monkeypatch.setattr(app_state, "settings", custom_settings)
    roots = get_scan_roots()
    assert str(tmp_path / "archive1") in roots
    assert str(tmp_path / "archive2") in roots
    assert str(tmp_path / "lib") in roots
    assert str(tmp_path / "dl") in roots


def test_get_scan_roots_fallback_cold_storage_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from galleryvault.app.dependencies import get_scan_roots
    from galleryvault.app.state import app_state
    from galleryvault.config import Settings

    custom_settings = Settings(
        library_roots=[str(tmp_path / "lib")],
        download_root=str(tmp_path / "dl"),
        cold_storage_root=str(tmp_path / "cold"),
    )
    monkeypatch.setattr(app_state, "settings", custom_settings)
    roots = get_scan_roots()
    assert str(tmp_path / "cold") in roots


def test_delete_local_copy_in_archive_root_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from galleryvault.app.state import app_state
    from galleryvault.config import Settings
    from galleryvault.services.deletion import delete_local_copy

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    target_file = archive_dir / "old_gallery.cbz"
    target_file.write_bytes(b"data")

    custom_settings = Settings(
        library_roots=[str(tmp_path / "lib")],
        download_root=str(tmp_path / "dl"),
        archive_roots=[str(archive_dir)],
    )
    monkeypatch.setattr(app_state, "settings", custom_settings)

    assert delete_local_copy(target_file) is True
    assert not target_file.exists()


def test_infer_category_metadata_and_parent_fallback(tmp_path: Path) -> None:
    from galleryvault.scanners.base import infer_category

    # 1. Metadata has valid category -> normalized
    cat_dir = tmp_path / "somedir" / "123-title"
    assert infer_category(cat_dir, {"category": "Doujinshi"}) == "doujinshi"
    assert infer_category(cat_dir, {"category": "MANGA"}) == "manga"

    # 2. Metadata has misc/other -> falls back to parent directory if valid
    manga_dir = tmp_path / "Manga" / "123-title"
    assert infer_category(manga_dir, {"category": "misc"}) == "manga"
    assert infer_category(manga_dir, {"category": "other"}) == "manga"

    # 3. No category in metadata -> infers from parent directory
    cg_dir = tmp_path / "Artist CG" / "456-title"
    assert infer_category(cg_dir, {}) == "artistcg"
    assert infer_category(cg_dir, None) == "artistcg"

    # 4. Neither metadata nor parents contain valid category -> fallback to misc
    unknown_dir = tmp_path / "UnknownParent" / "Subdir" / "789-title"
    assert infer_category(unknown_dir, {}) == "misc"

