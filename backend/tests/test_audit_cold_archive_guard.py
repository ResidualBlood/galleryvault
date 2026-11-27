"""Fail-closed guards for cold-archive adoption and source purging (audit T1).

Deleting the only source is only allowed when the cold copy provably covers it:
the destination must exist, be readable, contain real image pages (not just
metadata), and have at least as many pages as the source.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from galleryvault.app.state import app_state
from galleryvault.services.cold_archive import (
    _check_physically_archived,
    archive_one,
    cold_copy_covers_source,
    compute_cold_path,
    purge_archived_sources_internal,
)


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


def test_cold_copy_covers_source_rejects_metadata_only_directory(tmp_path: Path) -> None:
    source = tmp_path / "downloads" / "501-gallery"
    _write_pages(source, 3)
    dest = tmp_path / "cold" / "dir" / "aa" / "bb" / "501"
    dest.mkdir(parents=True)
    (dest / "ComicInfo.xml").write_bytes(b"<xml/>")
    (dest / ".galleryvault.json").write_text(json.dumps({"gid": 501}), encoding="utf-8")

    assert cold_copy_covers_source(source, dest) is False
    assert _check_physically_archived(501, [tmp_path / "cold"], source=source) is False


def test_cold_copy_covers_source_requires_at_least_source_pages(tmp_path: Path) -> None:
    source = tmp_path / "downloads" / "601-gallery"
    _write_pages(source, 3)
    stale = tmp_path / "cold" / "cbz" / "601.cbz"
    _write_cbz(stale, 1)
    full = tmp_path / "cold" / "cbz" / "602.cbz"
    _write_cbz(full, 3)

    assert cold_copy_covers_source(source, stale) is False
    assert cold_copy_covers_source(source, full) is True


async def test_archive_one_refuses_stale_single_page_cbz(tmp_path: Path, monkeypatch) -> None:
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "ssd"
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "701-Stale Cold Gallery"
    _write_pages(source, 3)
    dest = compute_cold_path(cold_root, is_cbz=True, gid=701, title="Stale Cold Gallery")
    _write_cbz(dest, 1)

    class FakeGallery:
        id = 61
        gid = 701
        token = "tok701"
        title = "Stale Cold Gallery"
        storage_path = str(source)
        storage_type = "folder"
        storage_size = 300
        file_size = 300
        trashed = False
        path_hash = "hash701"
        page_count = 3
        cover_path = "01.jpg"

    gallery_obj = FakeGallery()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: object) -> bool:
            return False

        async def get(self, model: object, ident: int):
            from galleryvault.db.models import Gallery

            if model is Gallery and ident == 61:
                return gallery_obj
            return None

        async def scalar(self, stmt: object):
            return None

        async def execute(self, stmt: object) -> _Result:
            return _Result([])

        def add_all(self, items: object) -> None:
            pass

        async def commit(self) -> None:
            pass

    result = await archive_one(
        61,
        cold_root=cold_root,
        delete_source=True,
        session_factory=lambda: FakeSession(),
    )

    assert result is None
    # The only source survives and DB still points at it.
    assert source.exists()
    assert (source / "03.jpg").exists()
    assert gallery_obj.storage_path == str(source)
    assert dest.exists()


async def test_archive_one_adopts_covering_cold_destination(tmp_path: Path, monkeypatch) -> None:
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    download_root = tmp_path / "ssd"
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "702-Complete Cold Gallery"
    _write_pages(source, 2)
    dest = compute_cold_path(cold_root, is_cbz=True, gid=702, title="Complete Cold Gallery")
    _write_cbz(dest, 2)

    class FakeGallery:
        id = 62
        gid = 702
        token = "tok702"
        title = "Complete Cold Gallery"
        storage_path = str(source)
        storage_type = "folder"
        storage_size = 200
        file_size = 200
        trashed = False
        path_hash = "hash702"
        page_count = 2
        cover_path = "01.jpg"

    gallery_obj = FakeGallery()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: object) -> bool:
            return False

        async def get(self, model: object, ident: int):
            from galleryvault.db.models import Gallery

            if model is Gallery and ident == 62:
                return gallery_obj
            return None

        async def scalar(self, stmt: object):
            return None

        async def execute(self, stmt: object) -> _Result:
            return _Result([])

        def add_all(self, items: object) -> None:
            pass

        async def commit(self) -> None:
            pass

    result = await archive_one(
        62,
        cold_root=cold_root,
        delete_source=True,
        session_factory=lambda: FakeSession(),
    )

    assert result == dest
    assert not source.exists()
    assert gallery_obj.storage_path == str(dest)


async def test_purge_keeps_source_when_db_cold_path_missing(
    tmp_path: Path, monkeypatch
) -> None:
    download_root = tmp_path / "downloads"
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "801-gallery"
    _write_pages(source, 2)
    missing_dest = cold_root / "cbz" / "801.cbz"

    purged = await purge_archived_sources_internal(
        session_factory=lambda: _PurgeSession([(801, str(missing_dest))])
    )

    assert purged == 0
    assert source.exists()
    assert (source / "01.jpg").exists()


async def test_purge_keeps_source_when_cold_dir_is_metadata_only(
    tmp_path: Path, monkeypatch
) -> None:
    download_root = tmp_path / "downloads"
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "802-gallery"
    _write_pages(source, 2)
    dest = cold_root / "dir" / "aa" / "bb" / "802"
    dest.mkdir(parents=True)
    (dest / "ComicInfo.xml").write_bytes(b"<xml/>")

    purged = await purge_archived_sources_internal(
        session_factory=lambda: _PurgeSession([(802, str(dest))])
    )

    assert purged == 0
    assert source.exists()


async def test_purge_deletes_source_when_cold_copy_covers_it(
    tmp_path: Path, monkeypatch
) -> None:
    download_root = tmp_path / "downloads"
    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    _use_settings(monkeypatch, download_root, cold_root)

    source = download_root / "803-gallery"
    _write_pages(source, 2)
    dest = cold_root / "cbz" / "803.cbz"
    _write_cbz(dest, 2)

    purged = await purge_archived_sources_internal(
        session_factory=lambda: _PurgeSession([(803, str(dest))])
    )

    assert purged == 1
    assert not source.exists()


async def test_purge_skips_when_cold_root_is_offline(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    download_root = tmp_path / "downloads"
    offline_cold = tmp_path / "offline-cold"
    _use_settings(monkeypatch, download_root, offline_cold)

    source = download_root / "804-gallery"
    _write_pages(source, 1)
    dest = offline_cold / "cbz" / "804.cbz"

    with caplog.at_level("WARNING"):
        purged = await purge_archived_sources_internal(
            session_factory=lambda: _PurgeSession([(804, str(dest))])
        )

    assert purged == 0
    assert source.exists()
    assert any("offline or unreadable" in record.getMessage() for record in caplog.records)
