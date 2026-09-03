from pathlib import Path

import pytest

from galleryvault.scanners.archive import validate_archive_member
from galleryvault.scanners.ehviewer import IMAGE_EXTENSIONS
from galleryvault.scanners.pdf import PdfScanner
from galleryvault.scanners.sevenzip import SevenZipScanner


def test_sevenzip_images_and_rejects_traversal(tmp_path: Path) -> None:
    py7zr = pytest.importorskip("py7zr")
    (tmp_path / "2.jpg").write_bytes(b"aaaa")
    (tmp_path / "10.png").write_bytes(b"bbbb")
    good = tmp_path / "1-demo.7z"
    with py7zr.SevenZipFile(good, "w") as archive:
        archive.write(tmp_path / "2.jpg", "2.jpg")
        archive.write(tmp_path / "10.png", "10.png")
    meta = SevenZipScanner().scan(good)
    assert [p.name for p in meta.pages] == ["2.jpg", "10.png"]
    assert meta.storage_type == "7z"
    data = SevenZipScanner().open_page(meta, meta.pages[0]).read()
    assert data == b"aaaa"

    with pytest.raises(ValueError):
        validate_archive_member("../x.jpg", None)


def test_sevenzip_scan_extracts_images_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    py7zr = pytest.importorskip("py7zr")
    (tmp_path / "1.jpg").write_bytes(b"aaaa")
    (tmp_path / "payload.bin").write_bytes(b"not-an-image" * 64)
    archive_path = tmp_path / "1-mixed.7z"
    with py7zr.SevenZipFile(archive_path, "w") as archive:
        archive.write(tmp_path / "1.jpg", "1.jpg")
        archive.write(tmp_path / "payload.bin", "payload.bin")

    def forbid_extractall(*_a, **_k):
        raise AssertionError("extractall must not be used")

    monkeypatch.setattr(py7zr.SevenZipFile, "extractall", forbid_extractall)
    seen: list[list[str] | None] = []
    orig_read = getattr(py7zr.SevenZipFile, "read", None)
    if callable(orig_read):

        def spy_read(self, targets=None):
            seen.append(list(targets) if targets is not None else None)
            return orig_read(self, targets=targets)

        monkeypatch.setattr(py7zr.SevenZipFile, "read", spy_read)
    orig_extract = py7zr.SevenZipFile.extract

    def spy_extract(self, path=None, targets=None, **kwargs):
        seen.append(list(targets) if targets is not None else None)
        return orig_extract(self, path=path, targets=targets, **kwargs)

    monkeypatch.setattr(py7zr.SevenZipFile, "extract", spy_extract)

    meta = SevenZipScanner().scan(archive_path)
    assert [p.name for p in meta.pages] == ["1.jpg"]
    assert seen
    for targets in seen:
        assert targets is not None
        assert "payload.bin" not in targets
        assert all(Path(name).suffix.casefold() in IMAGE_EXTENSIONS for name in targets)


def test_pdf_without_images_warns(tmp_path: Path) -> None:
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    path = tmp_path / "empty.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as fh:
        writer.write(fh)
    meta = PdfScanner().scan(path)
    assert meta.pages == []
    assert any("no extractable" in w for w in meta.warnings)
