import json
from pathlib import Path

import pytest

from galleryvault.scanners import registry
from galleryvault.scanners.ehviewer import (
    BareImageDirScanner,
    JhentaiDirScanner,
    parse_jhentai_posted,
    parse_jhentai_tags,
)
from galleryvault.services.library import LibraryService


def _write_jhentai_dir(
    path: Path, *, gid: int = 2862805, pages: int = 3, tags: str = "artist:foo,language:english"
) -> None:
    path.mkdir(parents=True)
    metadata = {
        "gallery": {
            "gid": gid,
            "token": "tok123",
            "title": "[Artist] Sample",
            "category": "Doujinshi",
            "pageCount": pages,
            "galleryUrl": f"https://exhentai.org/g/{gid}/tok123/",
            "uploader": "uploader1",
            "publishTime": "2024-05-01 12:34:00",
            "downloadStatusIndex": 3,
            "insertTime": "2024-05-01 12:34:56",
            "downloadOriginalImage": False,
            "priority": 0,
            "sortOrder": 0,
            "groupName": "",
            "tags": tags,
            "sanitizedTitle": "[Artist] Sample",
        },
        "images": "[]",
    }
    (path / "metadata").write_text(json.dumps(metadata), encoding="utf-8")
    for i in range(1, pages + 1):
        (path / f"{i}.jpg").write_bytes(b"page")


def test_jhentai_dir_scan(tmp_path: Path) -> None:
    path = tmp_path / "2862805 - [Artist] Sample"
    _write_jhentai_dir(path)
    gallery = JhentaiDirScanner().scan(path)
    assert gallery.storage_type == "jhentai_dir"
    assert gallery.gid == 2862805
    assert gallery.token == "tok123"
    assert gallery.title == "[Artist] Sample"
    assert gallery.uploader == "uploader1"
    assert gallery.category == "doujinshi"
    assert gallery.posted_at is not None
    assert gallery.posted_at.strftime("%Y-%m-%d %H:%M") == "2024-05-01 12:34"
    assert gallery.posted_at.tzinfo is not None
    assert gallery.tags == [
        {"namespace": "artist", "name": "foo"},
        {"namespace": "language", "name": "english"},
    ]
    assert [p.name for p in gallery.pages] == ["1.jpg", "2.jpg", "3.jpg"]
    assert gallery.file_count == 3
    assert not gallery.warnings
    (path / "4.jpg").write_bytes(b"page")
    assert any(
        warning.startswith("page count mismatch")
        for warning in JhentaiDirScanner().scan(path).warnings
    )


def test_jhentai_metadata_validation(tmp_path: Path) -> None:
    scanner = JhentaiDirScanner()
    path = tmp_path / "1 - bad"
    path.mkdir()
    (path / "metadata").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JHenTai"):
        scanner.scan(path)
    (path / "metadata").write_text(json.dumps({"images": "[]"}), encoding="utf-8")
    with pytest.raises(TypeError, match="'gallery' must be an object"):
        scanner.scan(path)
    (path / "metadata").write_text(
        json.dumps({"gallery": {"gid": "not-an-int", "token": "t"}}), encoding="utf-8"
    )
    with pytest.raises(TypeError, match="gid must be an integer"):
        scanner.scan(path)


def test_jhentai_matches_ignores_other_metadata_files(tmp_path: Path) -> None:
    scanner = JhentaiDirScanner()
    path = tmp_path / "2 - other"
    path.mkdir()
    (path / "metadata").write_text('{"something": 1}', encoding="utf-8")
    assert not scanner.matches(path)
    assert scanner.matches(tmp_path) is False


def test_parse_jhentai_tags() -> None:
    assert parse_jhentai_tags("") == []
    assert parse_jhentai_tags("artist:foo, language:english") == [
        {"namespace": "artist", "name": "foo"},
        {"namespace": "language", "name": "english"},
    ]
    assert parse_jhentai_tags("solo") == [{"namespace": "misc", "name": "solo"}]
    assert parse_jhentai_tags(None) == []


def test_parse_jhentai_posted() -> None:
    assert parse_jhentai_posted("2024-05-01 12:34:00").strftime("%Y-%m-%d %H:%M:%S") == (
        "2024-05-01 12:34:00"
    )
    assert parse_jhentai_posted("2024-05-01 12:34").strftime("%Y-%m-%d %H:%M") == "2024-05-01 12:34"
    assert parse_jhentai_posted("2024-05-01").strftime("%Y-%m-%d") == "2024-05-01"
    assert parse_jhentai_posted("nonsense") is None
    assert parse_jhentai_posted(None) is None


def test_registry_prefers_jhentai_over_bare(tmp_path: Path) -> None:
    path = tmp_path / "2862805 - [Artist] Sample"
    _write_jhentai_dir(path)
    assert registry.for_path(path).storage_type == "jhentai_dir"
    assert BareImageDirScanner().matches(path) is True


def test_jhentai_incremental_signature(tmp_path: Path) -> None:
    path = tmp_path / "2862805 - [Artist] Sample"
    _write_jhentai_dir(path)
    service = LibraryService([tmp_path])
    _, first = service.scan()
    _, second = service.scan()
    assert first.success == 1 and second.skipped == 1
    (path / "1.jpg").write_bytes(b"changed")
    _, third = service.scan()
    assert third.success == 1
