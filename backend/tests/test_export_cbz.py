import zipfile
from pathlib import Path

import pytest

from galleryvault.services.export_cbz import (
    UnsafeExportPath,
    cbz_filename,
    is_cbz_file,
    pack_directory_cbz,
    resolve_page_file,
)


def test_is_cbz_file_passthrough(tmp_path: Path) -> None:
    archive = tmp_path / "g.cbz"
    archive.write_bytes(b"cbz")
    assert is_cbz_file(archive)
    folder = tmp_path / "dir"
    folder.mkdir()
    assert not is_cbz_file(folder)
    other = tmp_path / "g.zip"
    other.write_bytes(b"zip")
    assert not is_cbz_file(other)


def test_pack_directory_cbz_orders_and_stored(tmp_path: Path) -> None:
    gallery = tmp_path / "g-1"
    gallery.mkdir()
    (gallery / "b.png").write_bytes(b"png-bytes")
    (gallery / "a.jpg").write_bytes(b"jpg-bytes")
    dest = tmp_path / "out.cbz"
    pack_directory_cbz(gallery, [(0, "a.jpg"), (1, "b.png")], dest)
    with zipfile.ZipFile(dest) as zf:
        assert zf.namelist() == ["0000.jpg", "0001.png"]
        assert zf.read("0000.jpg") == b"jpg-bytes"
        assert zf.getinfo("0000.jpg").compress_type == zipfile.ZIP_STORED
        assert zf.getinfo("0001.png").compress_type == zipfile.ZIP_STORED


def test_resolve_page_file_rejects_escape(tmp_path: Path) -> None:
    gallery = tmp_path / "g"
    gallery.mkdir()
    (gallery / "ok.jpg").write_bytes(b"x")
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"nope")
    assert resolve_page_file(gallery, "ok.jpg") == (gallery / "ok.jpg").resolve()
    with pytest.raises(UnsafeExportPath):
        resolve_page_file(gallery, "../secret.txt")
    with pytest.raises(UnsafeExportPath):
        resolve_page_file(gallery, "..\\secret.txt")
    with pytest.raises(UnsafeExportPath):
        resolve_page_file(gallery, "/etc/passwd")
    with pytest.raises(FileNotFoundError):
        pack_directory_cbz(gallery, [(0, "missing.jpg")], tmp_path / "x.cbz")
    with pytest.raises(UnsafeExportPath):
        pack_directory_cbz(gallery, [(0, "../secret.txt")], tmp_path / "y.cbz")


def test_cbz_filename_sanitizes() -> None:
    name = cbz_filename('a/b:c*d?"', 12, 3)
    assert name.endswith(".cbz")
    assert "/" not in name and ":" not in name
