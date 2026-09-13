import json
import zipfile
from pathlib import Path

import pytest

from galleryvault.metadata.sidecar import (
    SIDECAR_FILENAME,
    build_galleryvault_json,
    normalize_category,
    normalize_p_tokens,
    normalize_posted,
    normalize_quality,
    normalize_tags,
    normalize_title_jpn,
    parse_galleryvault_json,
    read_galleryvault_json,
    write_galleryvault_json,
)

EXPECTED_15_KEYS = {
    "version",
    "gid",
    "token",
    "title",
    "title_jpn",
    "category",
    "quality",
    "tags",
    "p_tokens",
    "uploader",
    "posted",
    "rating",
    "file_count",
    "file_size",
    "site",
}


def test_build_galleryvault_json_full_fields() -> None:
    raw = build_galleryvault_json(
        gid=345678,
        token="b9c8d7e6f5",
        title="English Title",
        title_jpn="日本語タイトル",
        category="Doujinshi",
        quality="resample",
        tags=[
            {"namespace": "artist", "name": "sample_artist"},
            {"namespace": "female", "name": "long hair"},
        ],
        p_tokens=["abcdef01", "abcdef02"],
        uploader="alice",
        posted="2023-01-01T00:00:00Z",
        rating=4.5,
        file_count=2,
        file_size=123456,
        site="exhentai",
    )
    assert raw.endswith(b"\n")
    # ensure_ascii=False: Japanese characters are not escaped into \uXXXX
    assert "日本語タイトル".encode() in raw

    data = json.loads(raw.decode("utf-8"))
    assert set(data.keys()) == EXPECTED_15_KEYS
    assert data["version"] == 1
    assert data["gid"] == 345678
    assert data["token"] == "b9c8d7e6f5"
    assert data["title"] == "English Title"
    assert data["title_jpn"] == "日本語タイトル"
    assert data["category"] == "doujinshi"
    assert data["quality"] == "resample"
    assert data["tags"] == [
        {"namespace": "artist", "name": "sample_artist"},
        {"namespace": "female", "name": "long hair"},
    ]
    assert data["p_tokens"] == ["abcdef01", "abcdef02"]
    assert data["uploader"] == "alice"
    assert data["posted"] == "2023-01-01T00:00:00Z"
    assert data["rating"] == 4.5
    assert data["file_count"] == 2
    assert data["file_size"] == 123456
    assert data["site"] == "exhentai"


def test_build_galleryvault_json_defaults_and_normalization() -> None:
    raw = build_galleryvault_json(
        title="Only Title",
        title_jpn="99999",  # pure digits -> ""
        category="MANGA",  # upper case -> manga
        quality=None,  # unknown quality -> null
    )
    data = json.loads(raw.decode("utf-8"))

    # All 15 keys must exist, not omitted
    assert set(data.keys()) == EXPECTED_15_KEYS
    assert data["version"] == 1
    assert data["gid"] is None
    assert data["token"] is None
    assert data["title"] == "Only Title"
    assert data["title_jpn"] == ""
    assert data["category"] == "manga"
    assert data["quality"] is None
    assert data["tags"] == []
    assert data["p_tokens"] == []
    assert data["uploader"] is None
    assert data["posted"] is None
    assert data["rating"] is None
    assert data["file_count"] is None
    assert data["file_size"] is None
    assert data["site"] is None


def test_build_galleryvault_json_p_tokens_dense_and_gaps() -> None:
    # Dense tokens with empty strings for missing pages
    tokens = ["tok0", "", "tok2"]
    raw = build_galleryvault_json(title="Gaps", p_tokens=tokens)
    data = json.loads(raw.decode("utf-8"))
    assert data["p_tokens"] == ["tok0", "", "tok2"]


def test_parse_galleryvault_json_legacy_downloader() -> None:
    """Legacy downloader sidecar: has quality/category/title/tags, lacks gid/token/p_tokens."""
    legacy_downloader = {
        "category": "Doujinshi",
        "title": "Legacy Downloader Gallery",
        "title_jpn": "レガシー",
        "tags": [{"namespace": "artist", "name": "foo"}],
        "quality": "original",
    }
    parsed = parse_galleryvault_json(json.dumps(legacy_downloader))
    assert parsed["category"] == "doujinshi"
    assert parsed["quality"] == "original"
    assert parsed["title"] == "Legacy Downloader Gallery"
    assert parsed["title_jpn"] == "レガシー"
    assert parsed["tags"] == [{"namespace": "artist", "name": "foo"}]
    assert parsed["gid"] is None
    assert parsed["token"] is None
    assert parsed["p_tokens"] == []


def test_parse_galleryvault_json_legacy_cold_archive() -> None:
    """Legacy cold archive sidecar: has gid/token/p_tokens, lacks quality, category may be absent."""
    legacy_cold = {
        "gid": 123456,
        "token": "tokabc",
        "title": "Legacy Cold Gallery",
        "title_jpn": "",
        "tags": [{"namespace": "misc", "name": "test"}],
        "p_tokens": ["pt1", "pt2"],
    }
    parsed = parse_galleryvault_json(json.dumps(legacy_cold))
    assert parsed["gid"] == 123456
    assert parsed["token"] == "tokabc"
    assert parsed["quality"] is None
    assert parsed["category"] is None
    assert parsed["p_tokens"] == ["pt1", "pt2"]
    assert parsed["title"] == "Legacy Cold Gallery"


def test_parse_galleryvault_json_preserves_unknown_keys() -> None:
    data_with_extra = {
        "version": 1,
        "gid": 888,
        "token": "tok888",
        "title": "Custom",
        "extra_vendor_field": "kept_value",
        "nested_plugin": {"enabled": True},
    }
    parsed = parse_galleryvault_json(json.dumps(data_with_extra))
    assert parsed["extra_vendor_field"] == "kept_value"
    assert parsed["nested_plugin"] == {"enabled": True}
    assert parsed["gid"] == 888


def test_parse_galleryvault_json_tags_formats() -> None:
    # String tags "ns:name" or "name"
    data = {
        "title": "Tags Format",
        "tags": ["artist:alice", "female:big breasts", "solo"],
    }
    parsed = parse_galleryvault_json(json.dumps(data))
    assert parsed["tags"] == [
        {"namespace": "artist", "name": "alice"},
        {"namespace": "female", "name": "big breasts"},
        {"namespace": "misc", "name": "solo"},
    ]


def test_parse_galleryvault_json_invalid_inputs() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_galleryvault_json("")
    with pytest.raises(json.JSONDecodeError):
        parse_galleryvault_json(b"not json")
    with pytest.raises(TypeError):
        parse_galleryvault_json(b"[1, 2, 3]")
    with pytest.raises((TypeError, AttributeError)):
        parse_galleryvault_json(None)  # type: ignore[arg-type]


def test_write_and_read_galleryvault_json_directory(tmp_path: Path) -> None:
    target_dir = tmp_path / "gallery_dir"
    target_dir.mkdir()

    write_galleryvault_json(
        target_dir,
        gid=555,
        token="tok555",
        title="Dir Gallery",
        quality="resample",
        category="non-h",
    )

    sidecar_path = target_dir / SIDECAR_FILENAME
    assert sidecar_path.is_file()
    # Ensure no leftover temp files
    assert sorted(p.name for p in target_dir.iterdir()) == [SIDECAR_FILENAME]

    read_data = read_galleryvault_json(target_dir)
    assert read_data is not None
    assert read_data["gid"] == 555
    assert read_data["token"] == "tok555"
    assert read_data["title"] == "Dir Gallery"
    assert read_data["quality"] == "resample"
    assert read_data["category"] == "non-h"

    # Corrupted sidecar in directory returns None
    (target_dir / SIDECAR_FILENAME).write_text("invalid json content", encoding="utf-8")
    assert read_galleryvault_json(target_dir) is None


def test_read_galleryvault_json_zip(tmp_path: Path) -> None:
    cbz_file = tmp_path / "test.cbz"
    payload = {
        "version": 1,
        "gid": 777,
        "token": "tok777",
        "title": "Zip Gallery",
        "quality": "original",
    }
    with zipfile.ZipFile(cbz_file, "w") as zf:
        zf.writestr(SIDECAR_FILENAME, json.dumps(payload))
        zf.writestr("0001.jpg", b"image bytes")

    data = read_galleryvault_json(cbz_file)
    assert data is not None
    assert data["gid"] == 777
    assert data["token"] == "tok777"
    assert data["quality"] == "original"

    # Zip without sidecar returns None
    empty_zip = tmp_path / "no_sidecar.cbz"
    with zipfile.ZipFile(empty_zip, "w") as zf:
        zf.writestr("0001.jpg", b"img")
    assert read_galleryvault_json(empty_zip) is None

    # Corrupted zip returns None
    corrupt_zip = tmp_path / "corrupt.cbz"
    corrupt_zip.write_bytes(b"not a real zip")
    assert read_galleryvault_json(corrupt_zip) is None


def test_normalizers() -> None:
    assert normalize_category("Doujinshi") == "doujinshi"
    assert normalize_category("MANGA") == "manga"
    assert normalize_category("NON-H") == "non-h"
    assert normalize_category("") is None
    assert normalize_category(None) is None

    assert normalize_quality("original") == "original"
    assert normalize_quality("ORIGINAL") == "original"
    assert normalize_quality("resample") == "resample"
    assert normalize_quality("invalid") is None
    assert normalize_quality(None) is None

    assert normalize_title_jpn("日本語") == "日本語"
    assert normalize_title_jpn("1234567") == ""  # pure digits
    assert normalize_title_jpn("   ") == ""
    assert normalize_title_jpn(None) == ""

    assert normalize_p_tokens(["tok1", "tok2"]) == ["tok1", "tok2"]
    assert normalize_p_tokens(None) == []

    assert normalize_tags(["artist:alice", "solo"]) == [
        {"namespace": "artist", "name": "alice"},
        {"namespace": "misc", "name": "solo"},
    ]
    assert normalize_tags(None) == []

    assert normalize_posted("2024-01-01T12:00:00Z") == "2024-01-01T12:00:00Z"
    assert normalize_posted(None) is None
