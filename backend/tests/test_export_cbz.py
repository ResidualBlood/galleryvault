import base64
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from galleryvault.app.main import app
from galleryvault.app.state import app_state
from galleryvault.auth import create_session, hash_password
from galleryvault.config import get_settings
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


@pytest.fixture
def export_test_client():
    original = app_state.settings
    base = (
        original
        if hasattr(original, "model_copy")
        else (app.state.settings if hasattr(app.state.settings, "model_copy") else get_settings())
    )
    updated = base.model_copy(
        update={
            "auth_required": True,
            "auth_secret": "unit-test-secret",
            "auth_password_hash": hash_password("export-pass"),
            "auth_password": None,
        }
    )
    app_state.settings = updated
    app.state.settings = updated
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app_state.settings = original
        app.state.settings = original


def _make_basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def test_export_cbz_unauthenticated_returns_401(
    export_test_client: TestClient,
) -> None:
    resp = export_test_client.get("/api/galleries/123/export.cbz")
    assert resp.status_code == 401
    # CBZ is no longer a basic auth route, so no WWW-Authenticate realm header
    assert resp.headers.get("www-authenticate") is None
    assert resp.json() == {"detail": "Authentication required"}


def test_export_cbz_basic_auth_alone_rejected(
    export_test_client: TestClient,
) -> None:
    # Basic Auth alone (without valid session cookie) is rejected with 401
    resp = export_test_client.get(
        "/api/galleries/123/export.cbz",
        headers={"authorization": _make_basic_auth("galleryvault", "export-pass")},
    )
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") is None


def test_export_cbz_valid_auth_success(
    export_test_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import galleries as galleries_router

    cbz_file = tmp_path / "valid.cbz"
    cbz_file.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # dummy empty zip
    row = SimpleNamespace(
        id=123,
        gid=456,
        title="Sample Gallery",
        storage_path=str(cbz_file),
    )

    async def fake_gallery(identifier: int):
        assert identifier == 123
        return row, []

    monkeypatch.setattr(galleries_router, "_gallery", fake_gallery)

    # Valid session cookie allows export
    export_test_client.cookies.set(
        "galleryvault_session", create_session("unit-test-secret", 60)
    )
    resp_cookie = export_test_client.get("/api/galleries/123/export.cbz")
    assert resp_cookie.status_code == 200
    assert resp_cookie.headers.get("content-type") == "application/zip"


def test_export_cbz_directory_anchors_to_download_root(
    export_test_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galleryvault.app.routers import galleries as galleries_router

    dl_root = tmp_path / "downloads"
    dl_root.mkdir()
    export_test_client.app.state.settings.download_root = str(dl_root)
    app_state.settings.download_root = str(dl_root)

    gallery_dir = tmp_path / "gdir"
    gallery_dir.mkdir()
    page1 = gallery_dir / "0001.jpg"
    page1.write_bytes(b"imgdata")

    page_row = SimpleNamespace(page_index=0, member_name="0001.jpg")
    row = SimpleNamespace(
        id=789,
        gid=101,
        title="Dir Gallery",
        storage_path=str(gallery_dir),
    )

    async def fake_gallery(identifier: int):
        return row, [page_row]

    monkeypatch.setattr(galleries_router, "_gallery", fake_gallery)

    export_test_client.cookies.set(
        "galleryvault_session", create_session("unit-test-secret", 60)
    )
    resp = export_test_client.get("/api/galleries/789/export.cbz")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/zip"

    # Verify .exports directory was created under download_root
    exports_dir = dl_root / ".exports"
    assert exports_dir.is_dir()
    # Temporary files should have been cleaned up after response
    remaining = list(exports_dir.glob("*.cbz"))
    assert remaining == []
