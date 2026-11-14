"""Characterisation tests for the single cold delete gate (T10.1b).

Deleting a copy is only allowed when ``verify.may_delete_copy(keep, drop)``
proves, via :func:`cold_copy_covers_source`, that the retained copy contains at
least every page of the dropped one.  The four destructive cold-storage sites
share that gate:

* adopting an existing cold pack (``orchestrate._do_archive_locked``),
* deleting the hot source after a successful archive,
* purging leftover sources of archived galleries,
* deleting the cold pack after a restore (``restore._remove_cold_pack``).

Each site gets one "does not cover -> nothing is deleted" case and one
"covers -> deleted" case, so the gate stays fail-closed at every call site.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from galleryvault.app.state import app_state
from galleryvault.services.cold import orchestrate as cold_orchestrate
from galleryvault.services.cold.paths import compute_cold_path
from galleryvault.services.cold.restore import _remove_cold_pack
from galleryvault.services.cold.verify import may_delete_copy


def _write_pages(directory: Path, count: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for idx in range(count):
        (directory / f"{idx + 1:02d}.jpg").write_bytes(b"page")


def _write_cbz(path: Path, page_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for idx in range(page_count):
            zf.writestr(f"{idx + 1:04d}.jpg", b"cold")
        zf.writestr("ComicInfo.xml", b"<xml/>")


def _use_settings(monkeypatch: pytest.MonkeyPatch, download_root: Path, cold_root: Path) -> None:
    monkeypatch.setattr(
        app_state,
        "settings",
        SimpleNamespace(
            download_root=str(download_root),
            library_roots=[],
            archive_roots=[str(cold_root)],
            cold_storage_root=str(cold_root),
            archive_root=None,
        ),
    )


class _Result:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)


class _PurgeSession:
    """Minimal async session matching the three queries purge performs."""

    def __init__(self, rows: list[tuple[int, str]], active_gids: list[int] | None = None) -> None:
        self.rows = rows
        self.active_gids = active_gids or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def execute(self, stmt: object) -> _Result:
        return _Result(list(self.rows))

    async def scalars(self, stmt: object) -> _Result:
        sql = str(stmt)
        if "download_tasks" in sql:
            return _Result(list(self.active_gids))
        return _Result([sp for _, sp in self.rows])


class _FakeGallery:
    def __init__(self, ident: int, gid: int, title: str, storage_path: Path) -> None:
        self.id = ident
        self.gid = gid
        self.token = f"tok{gid}"
        self.title = title
        self.title_jpn = None
        self.storage_path = str(storage_path)
        self.storage_type = "folder"
        self.storage_size = 200
        self.file_size = 200
        self.trashed = False
        self.path_hash = f"hash{gid}"
        self.page_count = 2
        self.cover_path = "01.jpg"


class _ArchiveSession:
    """Minimal async session for ``_do_archive_locked`` single-gallery runs."""

    def __init__(self, gallery: _FakeGallery) -> None:
        self.gallery = gallery

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def get(self, model: object, ident: int):
        from galleryvault.db.models import Gallery

        if model is Gallery and ident == self.gallery.id:
            return self.gallery
        return None

    async def scalar(self, stmt: object):
        return None

    async def execute(self, stmt: object) -> _Result:
        return _Result([])

    def add_all(self, items: object) -> None:
        pass

    async def commit(self) -> None:
        pass


# --- verify.may_delete_copy -------------------------------------------------


def test_gate_allows_delete_when_keep_covers_drop(tmp_path: Path) -> None:
    drop = tmp_path / "downloads" / "901-gallery"
    _write_pages(drop, 2)
    keep = tmp_path / "cold" / "cbz" / "901.cbz"
    _write_cbz(keep, 2)

    assert may_delete_copy(keep, drop) is True


def test_gate_refuses_delete_when_keep_has_fewer_pages(tmp_path: Path) -> None:
    drop = tmp_path / "downloads" / "902-gallery"
    _write_pages(drop, 3)
    keep = tmp_path / "cold" / "cbz" / "902.cbz"
    _write_cbz(keep, 2)

    assert may_delete_copy(keep, drop) is False


def test_gate_refuses_delete_of_the_kept_path_itself(tmp_path: Path) -> None:
    pages = tmp_path / "downloads" / "903-gallery"
    _write_pages(pages, 2)

    assert may_delete_copy(pages, pages) is False


def test_gate_refuses_delete_when_keep_is_missing(tmp_path: Path) -> None:
    drop = tmp_path / "downloads" / "904-gallery"
    _write_pages(drop, 1)

    assert may_delete_copy(tmp_path / "cold" / "cbz" / "904.cbz", drop) is False


def test_gate_falls_back_to_physical_cold_copy(tmp_path: Path) -> None:
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    drop = tmp_path / "downloads" / "905-gallery"
    _write_pages(drop, 2)
    _write_cbz(cold_root / "cbz" / "905.cbz", 2)

    assert may_delete_copy(None, drop, gid=905, cold_roots=[cold_root]) is True

    stale = tmp_path / "downloads" / "906-gallery"
    _write_pages(stale, 3)
    _write_cbz(cold_root / "cbz" / "906.cbz", 1)
    assert may_delete_copy(None, stale, gid=906, cold_roots=[cold_root]) is False


# --- site 1: adopt an existing cold pack ------------------------------------


async def test_adopt_refuses_non_covering_cold_destination(tmp_path: Path, monkeypatch) -> None:
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "ssd"
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "701-Partial Cold Gallery"
    _write_pages(source, 2)
    dest = compute_cold_path(cold_root, is_cbz=True, gid=701, title="Partial Cold Gallery")
    _write_cbz(dest, 1)  # does not cover the 2-page source

    gallery = _FakeGallery(71, 701, "Partial Cold Gallery", source)
    result = await cold_orchestrate.archive_one(
        71,
        cold_root=cold_root,
        delete_source=True,
        session_factory=lambda: _ArchiveSession(gallery),
    )

    assert result is None
    assert source.exists()
    assert (source / "02.jpg").exists()
    assert gallery.storage_path == str(source)


async def test_adopt_deletes_source_only_when_cold_copy_covers_it(
    tmp_path: Path, monkeypatch
) -> None:
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "ssd"
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "702-Complete Cold Gallery"
    _write_pages(source, 2)
    dest = compute_cold_path(cold_root, is_cbz=True, gid=702, title="Complete Cold Gallery")
    _write_cbz(dest, 2)

    gallery = _FakeGallery(72, 702, "Complete Cold Gallery", source)
    result = await cold_orchestrate.archive_one(
        72,
        cold_root=cold_root,
        delete_source=True,
        session_factory=lambda: _ArchiveSession(gallery),
    )

    assert result == dest
    assert not source.exists()
    assert gallery.storage_path == str(dest)


# --- site 2: delete the hot source after archiving --------------------------


async def test_archive_refuses_source_delete_when_pack_does_not_cover(
    tmp_path: Path, monkeypatch
) -> None:
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "ssd"
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "703-Short Pack"
    _write_pages(source, 2)

    def _short_pack(**kwargs: object) -> Path:
        dest = compute_cold_path(
            Path(kwargs["cold_root"]),
            is_cbz=True,
            gid=kwargs["gid"],
            title=kwargs["title"],
        )
        _write_cbz(dest, 1)  # failure injection: pack lost a page
        return dest

    monkeypatch.setattr(cold_orchestrate, "cold_pack_gallery", _short_pack)

    gallery = _FakeGallery(73, 703, "Short Pack", source)
    result = await cold_orchestrate.archive_one(
        73,
        cold_root=cold_root,
        delete_source=True,
        session_factory=lambda: _ArchiveSession(gallery),
    )

    assert result is not None
    assert result.exists()
    assert source.exists()
    assert (source / "02.jpg").exists()
    # The DB points at the cold copy, the source is kept as the safety copy.
    assert gallery.storage_path == str(result)


async def test_archive_deletes_source_when_pack_covers(tmp_path: Path, monkeypatch) -> None:
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "ssd"
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "704-Full Pack"
    _write_pages(source, 2)

    gallery = _FakeGallery(74, 704, "Full Pack", source)
    result = await cold_orchestrate.archive_one(
        74,
        cold_root=cold_root,
        delete_source=True,
        session_factory=lambda: _ArchiveSession(gallery),
    )

    assert result is not None
    assert result.is_file()
    assert not source.exists()


# --- site 3: purge leftover sources of archived galleries -------------------


async def test_purge_refuses_source_delete_when_cold_copy_does_not_cover(
    tmp_path: Path, monkeypatch
) -> None:
    download_root = tmp_path / "downloads"
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "801-gallery"
    _write_pages(source, 2)
    dest = cold_root / "cbz" / "801.cbz"
    _write_cbz(dest, 1)

    purged = await cold_orchestrate.purge_archived_sources_internal(
        session_factory=lambda: _PurgeSession([(801, str(dest))])
    )

    assert purged == 0
    assert source.exists()
    assert (source / "02.jpg").exists()


async def test_purge_deletes_source_when_cold_copy_covers_it(tmp_path: Path, monkeypatch) -> None:
    download_root = tmp_path / "downloads"
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "802-gallery"
    _write_pages(source, 2)
    dest = cold_root / "cbz" / "802.cbz"
    _write_cbz(dest, 2)

    purged = await cold_orchestrate.purge_archived_sources_internal(
        session_factory=lambda: _PurgeSession([(802, str(dest))])
    )

    assert purged == 1
    assert not source.exists()


# --- site 4: delete the cold pack after a restore ---------------------------


def test_remove_cold_pack_refuses_when_restored_copy_does_not_cover(tmp_path: Path) -> None:
    cold_pack = tmp_path / "cold" / "cbz" / "901.cbz"
    _write_cbz(cold_pack, 3)
    restored = tmp_path / "downloads" / "901-gallery"
    _write_pages(restored, 2)

    assert _remove_cold_pack(cold_pack, restored) is False
    assert cold_pack.exists()


def test_remove_cold_pack_deletes_pack_when_restored_copy_covers(tmp_path: Path) -> None:
    cold_pack = tmp_path / "cold" / "cbz" / "902.cbz"
    _write_cbz(cold_pack, 2)
    restored = tmp_path / "downloads" / "902-gallery"
    _write_pages(restored, 2)

    assert _remove_cold_pack(cold_pack, restored) is True
    assert not cold_pack.exists()


def test_remove_cold_pack_refuses_directory_pack_when_copy_is_partial(tmp_path: Path) -> None:
    cold_pack = tmp_path / "cold" / "dir" / "903"
    _write_pages(cold_pack, 2)
    (cold_pack / "ComicInfo.xml").write_bytes(b"<xml/>")
    restored = tmp_path / "downloads" / "903-gallery"
    _write_pages(restored, 1)

    assert _remove_cold_pack(cold_pack, restored) is False
    assert cold_pack.is_dir()
    assert (cold_pack / "01.jpg").exists()
