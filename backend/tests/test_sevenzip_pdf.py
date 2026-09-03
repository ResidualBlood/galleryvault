from pathlib import Path

import pytest

from galleryvault.scanners.archive import validate_archive_member
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
