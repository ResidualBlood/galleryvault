"""Tests for the shared local-deletion helper (delete_galleries_local).

Covers multi-copy collection, directory vs. single-file (CBZ) deletion,
partial-failure keeping the DB row, and duplicate_records cleanup after a
full multi-copy delete.
"""

from pathlib import Path

import pytest

from galleryvault.app.schemas import FilteredDeleteRequest
from galleryvault.app.state import app_state
from galleryvault.db.models import DuplicateRecord, Gallery
from galleryvault.services import deletion
from galleryvault.services.deletion import delete_galleries_local, delete_local_copy


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
    """Point get_scan_roots at tmp_path so _in_scan_roots passes tmp paths."""
    from galleryvault.app import dependencies

    monkeypatch.setattr(dependencies, "get_scan_roots", lambda: [str(tmp_path)])
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
    results = await delete_galleries_local(
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
    results = await delete_galleries_local(
        session, [gallery], delete_files=True, delete_all_copies=False
    )

    assert not archive.exists()
    assert results[0]["db_removed"] is True


@pytest.mark.asyncio
async def test_delete_outside_scan_roots_safely_blocked(tmp_path, monkeypatch):
    """A path outside the scan roots is blocked by security boundary; file is preserved."""
    outside = tmp_path.parent / "outside-gv"
    outside.mkdir(exist_ok=True)
    copy = outside / "g-3"
    copy.mkdir()
    gallery = _gallery(3, 333, copy)

    session = _session_factory([gallery], {})
    results = await delete_galleries_local(
        session, [gallery], delete_files=True, delete_all_copies=False
    )

    assert copy.exists()
    assert results[0]["db_removed"] is False
    assert results[0]["deleted_paths"] == []
    assert results[0]["failed_paths"] == [str(copy)]


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
    results = await delete_galleries_local(
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

    real = delete_local_copy

    def flaky(path, scan_roots=None):
        if Path(path) == bad:
            return False
        return real(path, scan_roots)

    monkeypatch.setattr(deletion, "delete_local_copy", flaky)

    session = _session_factory([gallery], {555: dup})
    results = await delete_galleries_local(
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
    results = await delete_galleries_local(
        session, [gallery], delete_files=False, delete_all_copies=False
    )

    assert copy.exists()
    assert results[0]["db_removed"] is True
    assert results[0]["failed_paths"] == []
    assert session.deleted_galleries == [6]


def test_chunked_splits_into_batches():
    """_chunked must keep every ``in_`` query under the asyncpg 32767 limit."""
    from galleryvault.db.repository import _chunked

    assert _chunked([]) == []
    assert _chunked([1]) == [[1]]
    chunks = _chunked(list(range(1500)))
    assert len(chunks) == 3
    assert [len(c) for c in chunks] == [500, 500, 500]
    assert chunks[0][0] == 0 and chunks[-1][-1] == 1499


async def _capture_in_sizes(session, statement, collector):
    """Run a scalars/execute against a no-op session and record ``in_`` sizes."""
    import re

    from sqlalchemy.dialects import postgresql

    compiled = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    for match in re.finditer(r"\bIN \(([0-9, ]+)\)", compiled):
        collector.append(len([v for v in match.group(1).split(",") if v.strip()]))
    return _EmptyResult()


class _EmptyResult:
    def all(self):
        return []

    def scalars(self):
        return self

    def __iter__(self):
        return iter(())


@pytest.mark.asyncio
async def test_metadata_map_chunks_in_queries():
    """metadata_map must issue chunked gid lookups for large gid lists."""
    from galleryvault.db import repository as repo_module

    in_sizes: list[int] = []
    original = repo_module.GalleryRepository.metadata_map

    class RecordingSession:
        async def scalars(self, statement):
            await _capture_in_sizes(self, statement, in_sizes)
            return _EmptyResult()

    repo = repo_module.GalleryRepository(RecordingSession())
    result = await original(repo, list(range(1200)))
    assert result == {}
    assert in_sizes and max(in_sizes) <= 500
    assert sum(in_sizes) >= 1200


@pytest.mark.asyncio
async def test_galleries_for_gids_chunks_in_queries():
    """Favorites remove-path lookups must stay under asyncpg's param limit."""
    from galleryvault.db import repository as repo_module

    in_sizes: list[int] = []
    original = repo_module.FavoritesRepository.galleries_for_gids

    class RecordingSession:
        async def execute(self, statement):
            await _capture_in_sizes(self, statement, in_sizes)
            return _EmptyResult()

    repo = repo_module.FavoritesRepository(RecordingSession())
    result = await original(repo, list(range(1200)))
    assert result == {}
    assert in_sizes and max(in_sizes) <= 500
    assert sum(in_sizes) >= 1200


@pytest.mark.asyncio
async def test_favorite_items_detail_by_gids_chunks_in_queries():
    """favorite_items_detail_by_gids must chunk both the main and tag queries."""
    from galleryvault.db import repository as repo_module

    in_sizes: list[int] = []
    original = repo_module.FavoritesRepository.favorite_items_detail_by_gids

    class RecordingSession:
        async def execute(self, statement):
            await _capture_in_sizes(self, statement, in_sizes)
            return _EmptyResult()

    repo = repo_module.FavoritesRepository(RecordingSession())
    result = await original(repo, list(range(1200)))
    assert result == {}
    assert in_sizes and max(in_sizes) <= 500
    assert len(in_sizes) >= 3  # 1200 gids -> 3 chunks; tag query gated by local rows


@pytest.mark.asyncio
async def test_delete_filtered_pages_and_chunks(monkeypatch):
    """delete-filtered must page the filter and delete in 500-row batches."""
    from galleryvault.app.routers import galleries as galleries_module
    from galleryvault.app.routers.galleries import delete_galleries_filtered

    galleries = [Gallery(id=i, gid=1000 + i, title=f"g{i}", storage_path="") for i in range(1, 1201)]
    page_calls = []
    deleted_batches = []

    class Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

        def __iter__(self):
            return iter(self._rows)

    class Session:
        def __init__(self):
            self._by_id = {g.id: g for g in galleries}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def begin(self):
            return self

        async def scalars(self, statement):
            import re

            from sqlalchemy.dialects import postgresql

            compiled = str(
                statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
            )
            ids = [
                int(v)
                for m in re.finditer(r"\bIN \(([0-9, ]+)\)", compiled)
                for v in m.group(1).split(",")
                if v.strip()
            ]
            return Result([self._by_id[i] for i in ids if i in self._by_id])

    session = Session()
    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: session

    class Repo:
        def __init__(self, session):
            self.session = session

        async def list_page(self, page, page_size, q, tags, *args, **kwargs):
            category = kwargs.get("category")
            exclude_favorited = kwargs.get("exclude_favorited", False)
            tag_mode = kwargs.get("tag_mode", "or")
            tag_match = kwargs.get("tag_match", "exact")
            page_calls.append((page, page_size, q, tags, tag_mode, tag_match, category, exclude_favorited))
            start = (page - 1) * page_size
            return len(galleries), galleries[start : start + page_size]

    monkeypatch.setattr(galleries_module, "GalleryRepository", Repo)

    async def fake_delete(session, batch, *, delete_files, delete_all_copies):
        deleted_batches.append(len(batch))
        return [
            {"gallery_id": g.id, "gid": g.gid, "db_removed": True, "deleted_paths": [], "failed_paths": []}
            for g in batch
        ]

    monkeypatch.setattr(galleries_module, "delete_galleries_local", fake_delete)

    try:
        body = FilteredDeleteRequest(q="", category=None, tags="", tag_mode="or", delete_files=False)
        result = await delete_galleries_filtered(body)
        assert result["matched"] == 1200
        assert result["deleted"] == 1200
        assert len(page_calls) == 3  # 1200 rows / 500 per page
        assert deleted_batches == [500, 500, 200]
    finally:
        app_state.session_factory = orig_factory


@pytest.mark.asyncio
async def test_delete_filtered_category_not_fav_forwards_exclude_favorited(monkeypatch):
    """delete-filtered with the pseudo-category ``__not_fav__`` must translate it
    into ``exclude_favorited=True`` and a ``None`` category before paging."""
    from galleryvault.app.routers import galleries as galleries_module
    from galleryvault.app.routers.galleries import delete_galleries_filtered

    calls = []

    class Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def begin(self):
            return self

        async def scalars(self, statement):
            return Result([])

    session = Session()
    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: session

    class Repo:
        def __init__(self, session):
            self.session = session

        async def list_page(self, page, page_size, q, tags, *args, **kwargs):
            category = kwargs.get("category")
            exclude_favorited = kwargs.get("exclude_favorited", False)
            calls.append((category, exclude_favorited))
            return 0, []

    monkeypatch.setattr(galleries_module, "GalleryRepository", Repo)

    async def fake_delete(session, batch, *, delete_files, delete_all_copies):
        return []

    monkeypatch.setattr(galleries_module, "delete_galleries_local", fake_delete)

    try:
        body = FilteredDeleteRequest(q="", category="__not_fav__", tags="", tag_mode="or", delete_files=False)
        result = await delete_galleries_filtered(body)
        assert result["matched"] == 0
        assert calls and calls[0] == (None, True)
    finally:
        app_state.session_factory = orig_factory
