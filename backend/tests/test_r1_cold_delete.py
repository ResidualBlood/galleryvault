"""Cold-storage copies must stay deletable, without weakening root boundaries.

Regression coverage for the dedupe/delete boundary: archive roots
(``archive_roots`` / ``cold_storage_root``) are valid deletion targets exactly
like library/download roots, while a root directory itself, a path outside every
root, and a symlink that escapes a root stay refused.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from galleryvault.app.routers import duplicates
from galleryvault.app.routers.duplicates import DuplicateResolveRequest, resolve_duplicate
from galleryvault.app.state import app_state
from galleryvault.services import deletion
from galleryvault.services.cold_archive import resolve_archive_roots


def _make_layout(tmp_path: Path) -> dict[str, Path]:
    library = tmp_path / "library"
    downloads = tmp_path / "downloads"
    archive = tmp_path / "archive"
    cold = tmp_path / "cold"
    for path in (library, downloads, archive, cold):
        path.mkdir()
    return {
        "library": library,
        "downloads": downloads,
        "archive": archive,
        "cold": cold,
    }


def _use_settings(monkeypatch, layout: dict[str, Path], *, cold_only: bool = False) -> None:
    """Configure roots like ``Settings.model_post_init`` does.

    ``cold_storage_root`` always mirrors the first archive root, so ``cold_only``
    exercises the legacy single-root configuration instead.
    """
    if cold_only:
        archive_roots: list[str] = []
        cold_root = str(layout["cold"])
    else:
        archive_roots = [str(layout["archive"])]
        cold_root = str(layout["archive"])
    settings = SimpleNamespace(
        library_roots=[str(layout["library"])],
        download_root=str(layout["downloads"]),
        archive_roots=archive_roots,
        archive_root=None,
        cold_storage_root=cold_root,
    )
    monkeypatch.setattr(app_state, "settings", settings)


def _same_path_set(left, right) -> bool:
    return {Path(p).resolve() for p in left} == {Path(p).resolve() for p in right}


def test_duplicates_scan_roots_include_archive_roots(tmp_path, monkeypatch):
    layout = _make_layout(tmp_path)
    _use_settings(monkeypatch, layout)

    roots = duplicates._scan_roots()

    expected = {
        layout["library"].resolve(),
        layout["downloads"].resolve(),
        layout["archive"].resolve(),
    }
    assert {Path(p).resolve() for p in roots} == expected
    # A copy that lives in archive/cold storage is now inside the deletable roots.
    archived_copy = layout["archive"] / "cbz" / "aa" / "bb" / "111-title.cbz"
    assert duplicates._in_roots(archived_copy) is True


def test_duplicates_scan_roots_cold_only_configuration(tmp_path, monkeypatch):
    """archive_roots empty -> resolve_archive_roots falls back to cold_storage_root."""
    layout = _make_layout(tmp_path)
    _use_settings(monkeypatch, layout, cold_only=True)

    roots = [Path(p).resolve() for p in duplicates._scan_roots()]

    assert layout["cold"].resolve() in roots
    assert duplicates._in_roots(layout["cold"] / "dir" / "aa" / "bb" / "111") is True


def test_deletion_default_roots_include_archive_roots(tmp_path, monkeypatch):
    """deletion._scan_roots_default carries the archive roots even when the
    shared scan-root helper does not know about them."""
    from galleryvault.app import dependencies

    layout = _make_layout(tmp_path)
    _use_settings(monkeypatch, layout)
    monkeypatch.setattr(
        dependencies, "get_scan_roots", lambda: [str(layout["library"])]
    )

    roots = [Path(p).resolve() for p in deletion._scan_roots_default()]

    assert layout["library"].resolve() in roots
    assert layout["archive"].resolve() in roots
    assert _same_path_set(
        [str(p) for p in resolve_archive_roots()],
        [str(layout["archive"].resolve())],
    )


def test_deletion_default_roots_cold_only_configuration(tmp_path, monkeypatch):
    """Legacy cold_storage_root-only config stays a valid deletion root."""
    from galleryvault.app import dependencies

    layout = _make_layout(tmp_path)
    _use_settings(monkeypatch, layout, cold_only=True)
    monkeypatch.setattr(
        dependencies, "get_scan_roots", lambda: [str(layout["library"])]
    )

    roots = [Path(p).resolve() for p in deletion._scan_roots_default()]

    assert layout["cold"].resolve() in roots


def test_in_scan_roots_refuses_root_outside_and_symlink_escape(tmp_path, monkeypatch):
    layout = _make_layout(tmp_path)
    _use_settings(monkeypatch, layout, cold_only=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    # The configured root itself is never a deletion target.
    assert duplicates._in_roots(layout["cold"]) is False
    assert duplicates._in_roots(layout["library"]) is False
    assert duplicates._in_roots(layout["downloads"]) is False
    # Path outside every root.
    assert duplicates._in_roots(outside / "copy") is False
    # Symlink inside a root but pointing outside it (escape).
    escape = layout["cold"] / "escape"
    escape.symlink_to(outside, target_is_directory=True)
    assert duplicates._in_roots(escape / "copy") is False


def test_delete_local_copy_allows_cold_storage_dir_and_cbz(tmp_path, monkeypatch):
    layout = _make_layout(tmp_path)
    _use_settings(monkeypatch, layout, cold_only=True)
    from galleryvault.app import dependencies

    monkeypatch.setattr(dependencies, "get_scan_roots", lambda: [str(layout["library"])])

    cold_dir = layout["cold"] / "dir" / "aa" / "bb" / "111"
    cold_dir.mkdir(parents=True)
    (cold_dir / "page.jpg").write_bytes(b"x")
    cold_cbz = layout["cold"] / "cbz" / "aa" / "bb" / "111-title.cbz"
    cold_cbz.parent.mkdir(parents=True)
    cold_cbz.write_bytes(b"archive")

    assert deletion.delete_local_copy(cold_dir) is True
    assert not cold_dir.exists()
    assert deletion.delete_local_copy(cold_cbz) is True
    assert not cold_cbz.exists()


def test_delete_local_copy_refuses_root_outside_and_symlink_escape(tmp_path, monkeypatch):
    layout = _make_layout(tmp_path)
    _use_settings(monkeypatch, layout, cold_only=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_copy = outside / "111"
    outside_copy.mkdir()
    (outside_copy / "page.jpg").write_bytes(b"x")

    # Root itself.
    assert deletion.delete_local_copy(layout["cold"]) is False
    assert layout["cold"].exists()
    # Outside every configured root.
    assert deletion.delete_local_copy(outside_copy) is False
    assert outside_copy.exists()
    # Symlink escape: the link resolves outside the roots, so it is refused and
    # the target survives.
    escape = layout["cold"] / "escape"
    escape.symlink_to(outside_copy, target_is_directory=True)
    assert deletion.delete_local_copy(escape) is False
    assert outside_copy.exists()
    assert (outside_copy / "page.jpg").exists()


@pytest.mark.asyncio
async def test_resolve_duplicate_deletes_cold_storage_copies(tmp_path, monkeypatch):
    """The dedupe endpoint can finally clear a group whose copies live in cold storage."""
    layout = _make_layout(tmp_path)
    _use_settings(monkeypatch, layout, cold_only=True)
    chosen = layout["cold"] / "dir" / "aa" / "bb" / "111"
    other = layout["cold"] / "cbz" / "aa" / "bb" / "111-title.cbz"
    chosen.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    other.write_bytes(b"archive")

    groups = [
        {
            "gid": 111,
            "copies": [{"path": str(chosen)}, {"path": str(other)}],
        }
    ]
    deleted_gids: list[int] = []

    class _FakeRepo:
        def __init__(self, session):
            pass

        async def list_duplicates(self):
            return groups

        async def delete_duplicate(self, gid):
            deleted_gids.append(gid)
            return True

    class _FakeIngest:
        def __init__(self, session):
            pass

        async def ingest(self, metas):
            return None

    class _FakeSession:
        def begin(self):
            class _Ctx:
                async def __aenter__(self_inner):
                    return self_inner

                async def __aexit__(self_inner, *args):
                    return False

            return _Ctx()

    monkeypatch.setattr(duplicates, "GalleryRepository", _FakeRepo)
    monkeypatch.setattr(duplicates, "GalleryIngestService", _FakeIngest)
    monkeypatch.setattr(duplicates, "_scan_copy", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        duplicates, "resolve_session", AsyncMock(return_value=_FakeSession())
    )

    result = await resolve_duplicate(
        111, DuplicateResolveRequest(path=str(chosen), delete_others=True)
    )

    assert chosen.exists()  # the chosen copy is ingested, not deleted
    assert not other.exists()  # the stale cold copy is gone
    assert deleted_gids == [111]  # duplicate group no longer lingers
    assert result["failed_paths"] == []


@pytest.mark.asyncio
async def test_resolve_duplicate_still_rejects_path_outsides_roots(tmp_path, monkeypatch):
    layout = _make_layout(tmp_path)
    _use_settings(monkeypatch, layout, cold_only=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await resolve_duplicate(
            111, DuplicateResolveRequest(path=str(outside / "copy"), delete_others=False)
        )
    assert exc_info.value.status_code == 422
    assert not (outside / "copy").exists()


class _GalleryStub:
    def __init__(self, gallery_id: int, gid: int, storage_path: Path) -> None:
        self.id = gallery_id
        self.gid = gid
        self.storage_path = str(storage_path)
        self.trashed = False
        self.trashed_at = None
        self.updated_at = None


class _PurgeSession:
    """Minimal async session for the delete_galleries_local phases."""

    def __init__(self) -> None:
        self.deleted_ids: list[int] = []

    def begin(self):
        class _Ctx:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *args):
                return False

        return _Ctx()

    async def scalars(self, statement):
        class _Result:
            def all(self_inner):
                return []

        return _Result()

    async def get(self, model, pk):
        return None

    async def delete(self, model):
        self.deleted_ids.append(getattr(model, "id", None))

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_recycle_bin_purge_deletes_cold_storage_copy(tmp_path, monkeypatch):
    """Trash purge path (galleries.py purge -> delete_galleries_local) benefits too."""
    layout = _make_layout(tmp_path)
    _use_settings(monkeypatch, layout, cold_only=True)
    from galleryvault.app import dependencies

    monkeypatch.setattr(dependencies, "get_scan_roots", lambda: [str(layout["library"])])

    cold_copy = layout["cold"] / "dir" / "aa" / "bb" / "222"
    cold_copy.mkdir(parents=True)
    (cold_copy / "page.jpg").write_bytes(b"x")
    gallery = _GalleryStub(22, 222, cold_copy)
    session = _PurgeSession()

    results = await deletion.delete_galleries_local(
        session, [gallery], delete_files=True, delete_all_copies=False
    )

    assert not cold_copy.exists()
    assert results[0]["deleted_paths"] == [str(cold_copy)]
    assert results[0]["failed_paths"] == []
    assert results[0]["db_removed"] is True
    assert session.deleted_ids == [22]
