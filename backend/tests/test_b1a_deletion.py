"""Batch B1-A: deletion / duplicate-copy / updates-list boundary fixes.

Covers review 03 #9 (scan root itself as deletion target), #10 (duplicate record
dropped even when a copy survived), #16 (``state=active`` total vs. items) and
#21 (purge without file deletion reporting orphaned on-disk copies).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from galleryvault.app.routers import duplicates as dups
from galleryvault.app.routers import updates as updates_router
from galleryvault.app.routers.duplicates import DuplicateResolveRequest, resolve_duplicate
from galleryvault.app.state import app_state
from galleryvault.db.models import DuplicateRecord, Gallery
from galleryvault.db.repositories.updates import ACTIVE_STATE, _build_list_query
from galleryvault.services.deletion import (
    delete_galleries_local,
    delete_local_copy,
    in_scan_roots,
)


# --------------------------------------------------------------------------- #
# #9 scan-root boundary
# --------------------------------------------------------------------------- #
def test_in_scan_roots_rejects_scan_root_itself(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    child = root / "g-1"
    child.mkdir()

    assert in_scan_roots(child, [str(root)]) is True
    # ``is_relative_to`` is True for equal paths; the root itself must be refused.
    assert in_scan_roots(root, [str(root)]) is False
    assert in_scan_roots(Path("/"), [str(root)]) is False
    assert in_scan_roots(child, [str(tmp_path / "missing"), str(root)]) is True


def test_delete_local_copy_refuses_scan_root_itself(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "page.jpg").write_bytes(b"x")

    assert delete_local_copy(root, [str(root)]) is False
    assert root.is_dir()
    assert (root / "page.jpg").exists()


# --------------------------------------------------------------------------- #
# #21 purge (hard delete) without file deletion reports orphaned copies
# --------------------------------------------------------------------------- #
class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self):
        self.deleted_galleries: list[int] = []

    async def get(self, model, pk):
        if model is DuplicateRecord:
            return
        return

    async def scalars(self, statement):
        return _Result([])

    async def delete(self, model):
        if isinstance(model, Gallery):
            self.deleted_galleries.append(model.id)

    async def flush(self):
        pass

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


def _gallery(id_, gid, storage_path):
    return Gallery(id=id_, gid=gid, storage_path=str(storage_path), title=f"g{id_}")


@pytest.mark.asyncio
async def test_hard_delete_without_files_reports_orphan_paths(tmp_path):
    copy = tmp_path / "lib" / "g-1"
    copy.mkdir(parents=True)
    gallery = _gallery(1, 111, copy)
    session = _FakeSession()

    results = await delete_galleries_local(
        session,
        [gallery],
        delete_files=False,
        delete_all_copies=False,
        scan_roots=[str(tmp_path / "lib")],
        trash=False,
    )

    assert results[0]["db_removed"] is True
    assert results[0]["trashed"] is False
    assert results[0]["orphan_paths"] == [str(copy)]
    # the copy is intentionally kept, but is no longer tracked by any row
    assert copy.is_dir()
    assert session.deleted_galleries == [1]


@pytest.mark.asyncio
async def test_soft_delete_does_not_report_orphans(tmp_path):
    copy = tmp_path / "lib" / "g-2"
    copy.mkdir(parents=True)
    gallery = _gallery(2, 222, copy)
    session = _FakeSession()

    results = await delete_galleries_local(
        session,
        [gallery],
        delete_files=False,
        delete_all_copies=False,
        scan_roots=[str(tmp_path / "lib")],
    )

    assert results[0]["trashed"] is True
    assert results[0]["db_removed"] is False
    assert results[0]["orphan_paths"] == []
    assert copy.is_dir()


# --------------------------------------------------------------------------- #
# #10 duplicate resolve keeps the record when a copy survives
# --------------------------------------------------------------------------- #
class _ResolveSession:
    def in_transaction(self):
        return False

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


def _prepare_resolve(monkeypatch, tmp_path, copies_meta, fail_names=()):
    """Wire duplicate-resolve fakes; returns the recorder dict."""
    import shutil as real_shutil

    original_rmtree = real_shutil.rmtree

    recorder = {"deleted_duplicate": [], "groups": [{"gid": 4242, "copies": copies_meta}]}

    class FakeGalleryRepo:
        def __init__(self, session):
            pass

        async def list_duplicates(self):
            return recorder["groups"]

        async def delete_duplicate(self, gid):
            recorder["deleted_duplicate"].append(gid)
            recorder["groups"] = []

    class FakeIngestService:
        def __init__(self, session):
            pass

        async def ingest(self, metas):
            recorder["ingested"] = metas

    async def fake_scan_copy(path):
        return {"gid": 4242, "path": str(path), "title": "chosen"}

    async def _inline(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def _rmtree(path, *args, **kwargs):
        if Path(path).name in fail_names:
            raise PermissionError(f"cannot remove {path}")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(dups, "GalleryRepository", FakeGalleryRepo)
    monkeypatch.setattr(dups, "GalleryIngestService", FakeIngestService)
    monkeypatch.setattr(dups, "_scan_copy", fake_scan_copy)
    monkeypatch.setattr(dups, "_in_roots", lambda p: True)
    monkeypatch.setattr(dups, "run_in_threadpool", _inline)
    monkeypatch.setattr(dups.shutil, "rmtree", _rmtree)
    return recorder


@pytest.mark.asyncio
async def test_resolve_duplicate_partial_failure_keeps_duplicate_record(
    tmp_path, monkeypatch
):
    chosen = tmp_path / "chosen"
    chosen.mkdir()
    keep_failing = tmp_path / "fails"
    keep_failing.mkdir()
    ok_copy = tmp_path / "ok"
    ok_copy.mkdir()

    copies_meta = [
        {"path": str(chosen), "title": "chosen"},
        {"path": str(keep_failing), "title": "fails"},
        {"path": str(ok_copy), "title": "ok"},
    ]
    recorder = _prepare_resolve(monkeypatch, tmp_path, copies_meta, fail_names={"fails"})

    result = await resolve_duplicate(
        gid=4242,
        body=DuplicateResolveRequest(path=str(chosen), delete_others=True),
        session=_ResolveSession(),
    )

    # the surviving copy must stay tracked -> record is kept
    assert recorder["deleted_duplicate"] == []
    assert result["failed_paths"] == [str(keep_failing)]
    assert keep_failing.is_dir()
    assert not ok_copy.exists()


@pytest.mark.asyncio
async def test_resolve_duplicate_full_success_deletes_duplicate_record(
    tmp_path, monkeypatch
):
    chosen = tmp_path / "chosen"
    chosen.mkdir()
    ok_copy = tmp_path / "ok"
    ok_copy.mkdir()

    copies_meta = [
        {"path": str(chosen), "title": "chosen"},
        {"path": str(ok_copy), "title": "ok"},
    ]
    recorder = _prepare_resolve(monkeypatch, tmp_path, copies_meta)

    result = await resolve_duplicate(
        gid=4242,
        body=DuplicateResolveRequest(path=str(chosen), delete_others=True),
        session=_ResolveSession(),
    )

    assert recorder["deleted_duplicate"] == [4242]
    assert result["failed_paths"] == []
    assert not ok_copy.exists()


# --------------------------------------------------------------------------- #
# #16 updates list: "active" excludes ignored in SQL
# --------------------------------------------------------------------------- #
def test_build_list_query_active_excludes_ignored():
    sql = str(
        _build_list_query(ACTIVE_STATE).compile(compile_kwargs={"literal_binds": True})
    )
    assert "status != 'ignored'" in sql

    assert "ignored" not in str(_build_list_query(None).compile())
    ignored_sql = str(
        _build_list_query("ignored").compile(compile_kwargs={"literal_binds": True})
    )
    assert "status = 'ignored'" in ignored_sql


def _row(row_id, status):
    return SimpleNamespace(
        id=row_id,
        gallery_id=row_id * 10,
        old_gid=row_id * 100,
        new_gid=row_id * 1000,
        title=f"t{row_id}",
        favcat=0,
        status=status,
        error_message=None,
        detected_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00"),
        updated_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:01"),
    )


@pytest.mark.asyncio
async def test_updates_list_active_passes_active_filter(monkeypatch):
    seen: list[str | None] = []

    class FakeRepo:
        def __init__(self, session):
            pass

        async def list_page(self, page, page_size, status=None):
            seen.append(status)
            return 2, [_row(1, "pending"), _row(2, "failed")]

    class FakeFavRepo:
        def __init__(self, session):
            pass

        async def category_names(self, favcats):
            return {}

    class Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: Sess()
    monkeypatch.setattr(updates_router, "GalleryUpdatesRepository", FakeRepo)
    monkeypatch.setattr(updates_router, "FavoritesRepository", FakeFavRepo)

    try:
        body = await updates_router.gallery_updates_list(page=1, page_size=24, state="active")
    finally:
        app_state.session_factory = orig_factory

    assert seen == [ACTIVE_STATE]
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert [it["status"] for it in body["items"]] == ["pending", "failed"]
