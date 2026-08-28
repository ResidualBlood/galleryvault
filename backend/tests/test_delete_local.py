"""Tests for the shared local-deletion helper (main.delete_galleries_local).

Covers multi-copy collection, per-path scan-root validation, directory vs.
single-file (CBZ) deletion, partial-failure keeping the DB row, and
duplicate_records cleanup after a full multi-copy delete.
"""

from pathlib import Path

import pytest

from galleryvault.app import main
from galleryvault.db.models import DuplicateRecord, Gallery


def _session_factory(gallery_rows, dup_rows):
    """Build an in-memory session recording deletes against simple dict maps."""

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class Session:
        def __init__(self):
            self.galleries = {g.id: g for g in gallery_rows}
            self.dups = {g: r for g, r in dup_rows.items()}
            self.deleted_galleries = []
            self.deleted_dups = []

        async def get(self, model, pk):
            if model is DuplicateRecord:
                return self.dups.get(int(pk))
            return None

        async def scalars(self, statement):
            return _Result([])

        async def delete(self, model):
            if isinstance(model, Gallery):
                self.deleted_galleries.append(model.id)
            elif isinstance(model, DuplicateRecord):
                self.deleted_dups.append(model.gid)

        async def flush(self):
            pass

    return Session()


@pytest.fixture(autouse=True)
def _scan_roots_isolated(monkeypatch, tmp_path):
    """Point _scan_roots at tmp_path so _in_scan_roots passes tmp paths."""
    monkeypatch.setattr(main, "_scan_roots", lambda: [str(tmp_path)])
    return str(tmp_path)


def _gallery(id_, gid, storage_path):
    return Gallery(
        id=id_,
        gid=gid,
        storage_path=str(storage_path),
        title=f"g{id_}",
    )


@pytest.mark.asyncio
async def test_delete_single_directory(tmp_path):
    """A plain directory copy is deleted and the DB row removed."""
    copy = tmp_path / "g-1"
    copy.mkdir()
    (copy / "page.jpg").write_bytes(b"x")
    gallery = _gallery(1, 111, copy)

    session = _session_factory([gallery], {})
    results = await main.delete_galleries_local(
        session, [gallery], delete_files=True, delete_all_copies=False
    )

    assert not copy.exists()
    assert results[0]["db_removed"] is True
    assert results[0]["failed_paths"] == []
    assert session.deleted_galleries == [1]


@pytest.mark.asyncio
async def test_delete_single_cbz_file(tmp_path):
    """A single-file (CBZ/archive) gallery is unlinked, not rmtree'd."""
    archive = tmp_path / "g-2.cbz"
    archive.write_bytes(b"archive")
    gallery = _gallery(2, 222, archive)

    session = _session_factory([gallery], {})
    results = await main.delete_galleries_local(
        session, [gallery], delete_files=True, delete_all_copies=False
    )

    assert not archive.exists()
    assert results[0]["db_removed"] is True


@pytest.mark.asyncio
async def test_delete_outside_scan_roots_leaves_file_but_removes_row(tmp_path, monkeypatch):
    """A path outside the scan roots is never deleted, but the row still goes."""
    outside = tmp_path.parent / "outside-gv"
    outside.mkdir(exist_ok=True)
    copy = outside / "g-3"
    copy.mkdir()
    gallery = _gallery(3, 333, copy)

    session = _session_factory([gallery], {})
    results = await main.delete_galleries_local(
        session, [gallery], delete_files=True, delete_all_copies=False
    )

    assert copy.exists()  # outside scan root -> untouched
    assert results[0]["db_removed"] is True  # row still removed (not an error)
    assert results[0]["deleted_paths"] == []


@pytest.mark.asyncio
async def test_delete_all_copies_removes_every_copy_and_duplicate_record(tmp_path):
    """delete_all_copies=True deletes every physical copy + cleans the record."""
    a = tmp_path / "a-4"
    b = tmp_path / "b-4"
    a.mkdir()
    b.mkdir()
    gallery = _gallery(4, 444, a)
    dup = DuplicateRecord(
        gid=444,
        status="open",
        policy="keep_first",
        winner_path=str(a),
        copies=[{"path": str(a)}, {"path": str(b)}],
    )

    session = _session_factory([gallery], {444: dup})
    results = await main.delete_galleries_local(
        session, [gallery], delete_files=True, delete_all_copies=True
    )

    assert not a.exists() and not b.exists()
    assert results[0]["db_removed"] is True
    assert sorted(results[0]["deleted_paths"]) == sorted([str(a), str(b)])
    assert session.deleted_dups == [444]


@pytest.mark.asyncio
async def test_delete_partial_failure_keeps_db_row(tmp_path, monkeypatch):
    """A read-only copy fails -> the gallery row is kept (no resurrection)."""
    ok = tmp_path / "ok-5"
    bad = tmp_path / "bad-5"
    ok.mkdir()
    bad.mkdir()
    (bad / "locked").write_bytes(b"x")
    gallery = _gallery(5, 555, ok)
    dup = DuplicateRecord(
        gid=555,
        status="open",
        policy="keep_first",
        winner_path=str(ok),
        copies=[{"path": str(ok)}, {"path": str(bad)}],
    )

    real = main._delete_local_copy

    def flaky(path):
        if path == bad:
            return False
        return real(path)

    monkeypatch.setattr(main, "_delete_local_copy", flaky)

    session = _session_factory([gallery], {555: dup})
    results = await main.delete_galleries_local(
        session, [gallery], delete_files=True, delete_all_copies=True
    )

    assert not ok.exists() and bad.exists()  # successful copy gone, failed copy kept
    assert results[0]["db_removed"] is False  # row kept: not everything was deleted
    assert bad in [Path(p) for p in results[0]["failed_paths"]]
    assert session.deleted_galleries == []


@pytest.mark.asyncio
async def test_delete_files_false_only_removes_db_row(tmp_path):
    """delete_files=False never touches the disk but removes the row."""
    copy = tmp_path / "g-6"
    copy.mkdir()
    gallery = _gallery(6, 666, copy)

    session = _session_factory([gallery], {})
    results = await main.delete_galleries_local(
        session, [gallery], delete_files=False, delete_all_copies=False
    )

    assert copy.exists()
    assert results[0]["db_removed"] is True
    assert results[0]["failed_paths"] == []
    assert session.deleted_galleries == [6]
