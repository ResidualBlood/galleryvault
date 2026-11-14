"""T4.1: explicit ``galleries.storage_tier`` state.

DB-free tests: archive writes ``cold``, ingest derives the tier from the cold
roots, and the startup reconcile fixes historical rows idempotently.
"""

import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from galleryvault.db.models import Gallery


def _fake_archive_session(gallery_obj, pages_created: list) -> type:
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, model, ident):
            if model is Gallery and ident == gallery_obj.id:
                return gallery_obj
            return None

        async def scalar(self, stmt):
            return None

        async def execute(self, stmt):
            class Res:
                def all(self):
                    return []

            return Res()

        def add_all(self, items):
            pages_created.extend(items)

        async def commit(self):
            pass

    return FakeSession


@pytest.mark.asyncio
async def test_archive_marks_gallery_cold(tmp_path: Path) -> None:
    from galleryvault.services.cold_archive import archive_one

    cold_root = tmp_path / "cold"
    cold_root.mkdir()
    source = tmp_path / "ssd" / "300-Tier Gallery"
    source.mkdir(parents=True)
    (source / "01.jpg").write_bytes(b"page1")
    (source / "02.png").write_bytes(b"page2")

    class FakeGallery:
        id = 77
        gid = 300
        token = "tok300"
        title = "Tier Gallery"
        storage_path = str(source)
        storage_type = "folder"
        storage_size = 10
        file_size = 10
        trashed = False
        path_hash = "oldhash"
        page_count = 2
        cover_path = "01.jpg"
        storage_tier = "hot"
        cold_at = None

    gallery_obj = FakeGallery()
    pages_created: list = []
    dest = await archive_one(
        77,
        cold_root=cold_root,
        delete_source=True,
        session_factory=lambda: _fake_archive_session(gallery_obj, pages_created)(),
    )

    assert dest is not None and dest.is_file()
    assert gallery_obj.storage_path == str(dest)
    assert gallery_obj.storage_type == "cbz"  # format enum unchanged
    assert gallery_obj.storage_tier == "cold"
    assert isinstance(gallery_obj.cold_at, datetime)
    assert gallery_obj.cold_at.tzinfo is not None


def _gallery_meta(path: Path):
    from galleryvault.scanners.base import GalleryMeta

    return GalleryMeta(title="Cold Ingest", path=path, storage_type="folder", pages=[])


class _IngestSession:
    def __init__(self) -> None:
        self.added: list = []
        self.executed: list = []
        self.flushed = 0

    async def scalars(self, stmt):
        return SimpleNamespace(all=list)

    async def execute(self, stmt):
        self.executed.append(stmt)

        class Res:
            def all(self):
                return []

        return Res()

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, items):
        self.added.extend(items)

    async def flush(self):
        self.flushed += 1


@pytest.mark.asyncio
async def test_ingest_under_cold_root_sets_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.db.repositories.galleries_ingest import GalleryIngestMixin
    from galleryvault.services import cold_archive

    cold_root = tmp_path / "Archive"
    cold_root.mkdir()
    monkeypatch.setattr(
        cold_archive, "resolve_archive_roots", lambda *a, **k: [cold_root.resolve()]
    )

    session = _IngestSession()
    repo = GalleryIngestMixin()
    repo.session = session  # type: ignore[assignment]

    cold_path = cold_root / "cbz" / "aa" / "bb" / "301-Cold Ingest.cbz"
    await repo.upsert_many([_gallery_meta(cold_path)])

    rows = [obj for obj in session.added if isinstance(obj, Gallery)]
    assert len(rows) == 1
    assert rows[0].storage_tier == "cold"
    assert rows[0].cold_at is not None


@pytest.mark.asyncio
async def test_ingest_outside_cold_root_stays_hot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.db.repositories.galleries_ingest import GalleryIngestMixin
    from galleryvault.services import cold_archive

    cold_root = tmp_path / "Archive"
    cold_root.mkdir()
    monkeypatch.setattr(
        cold_archive, "resolve_archive_roots", lambda *a, **k: [cold_root.resolve()]
    )

    session = _IngestSession()
    repo = GalleryIngestMixin()
    repo.session = session  # type: ignore[assignment]

    await repo.upsert_many([_gallery_meta(tmp_path / "downloads" / "302-Hot")])

    rows = [obj for obj in session.added if isinstance(obj, Gallery)]
    assert len(rows) == 1
    assert rows[0].storage_tier == "hot"
    assert rows[0].cold_at is None


class _ReconcileSession:
    """Fake async session counting the bulk UPDATE statements, not ORM rows."""

    def __init__(self, checked: int, rowcounts: list[int]) -> None:
        self.checked = checked
        self.rowcounts = rowcounts
        self.statements: list = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def scalar(self, stmt):
        return self.checked

    async def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(rowcount=self.rowcounts[len(self.statements) - 1])

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_reconcile_uses_set_based_updates(tmp_path: Path) -> None:
    from galleryvault.services.cold_archive import reconcile_storage_tier

    cold_root = tmp_path / "Archive"
    cold_root.mkdir()
    # checked=3; cold fixed=1, cold_at filled=1, hot fixed=1
    session = _ReconcileSession(3, [1, 1, 1])

    counts = await reconcile_storage_tier(
        session_factory=lambda: session, archive_roots=[cold_root]
    )

    assert counts == {"checked": 3, "fixed_cold": 1, "fixed_hot": 1, "cold_at_filled": 1}
    assert session.commits == 1
    # Exactly three bulk UPDATEs; no select(Gallery) row hydration is possible
    # because this fake session has no ``scalars``/``get`` method.
    assert len(session.statements) == 3
    sql = " ".join(str(stmt) for stmt in session.statements)
    assert "UPDATE galleries" in sql
    # cold_at is backfilled in SQL from updated_at, not in Python per row.
    assert "updated_at" in sql
    assert "coalesce" in sql.lower()

    # Idempotent: a second pass reports no changes and does not commit.
    second = _ReconcileSession(3, [0, 0, 0])
    counts_again = await reconcile_storage_tier(
        session_factory=lambda: second, archive_roots=[cold_root]
    )
    assert counts_again == {
        "checked": 3,
        "fixed_cold": 0,
        "fixed_hot": 0,
        "cold_at_filled": 0,
    }
    assert second.commits == 0


def _matches_prefix(path: str, roots: list[str]) -> bool:
    from galleryvault.services.cold_archive import _normalize_root_prefix

    return any(
        path == _normalize_root_prefix(root)
        or path.startswith(_normalize_root_prefix(root) + os.sep)
        for root in roots
    )


@pytest.mark.asyncio
async def test_reconcile_without_cold_roots_never_marks_cold() -> None:
    from galleryvault.services.cold_archive import reconcile_storage_tier

    session = _ReconcileSession(5, [3])
    counts = await reconcile_storage_tier(session_factory=lambda: session, archive_roots=[])

    assert counts == {"checked": 5, "fixed_cold": 0, "fixed_hot": 3, "cold_at_filled": 0}
    # Only the hot reset ran; without a cold root no row may become cold.
    assert len(session.statements) == 1
    hot_sql = str(session.statements[0])
    assert "UPDATE galleries" in hot_sql
    assert "LIKE" not in hot_sql


def test_cold_prefix_boundary_matches_is_under_cold(tmp_path: Path) -> None:
    from galleryvault.services.cold_archive import _normalize_root_prefix, is_under_cold

    root = tmp_path / "Archive"
    root.mkdir()
    roots = [str(root)]
    cases = [
        (str(root), True),
        (str(root / "cbz" / "aa" / "1.cbz"), True),
        (str(tmp_path / "Archive2" / "x"), False),
        (str(tmp_path / "archive" / "x"), False),
        (str(tmp_path / "Other" / "x"), False),
    ]
    for path, expected in cases:
        assert _matches_prefix(path, roots) is expected, path
        # The SQL predicate mirrors this for stored absolute paths.
        assert is_under_cold(path, roots) is expected, path
    assert _normalize_root_prefix(str(root) + os.sep) == str(root)


def test_cold_path_filter_escapes_like_wildcards() -> None:
    from sqlalchemy.dialects import postgresql

    from galleryvault.services.cold_archive import _cold_path_filter

    condition = _cold_path_filter(["/Archive", "/Archive2", "/Arc_hive%x"])
    assert condition is not None
    compiled = condition.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    # The separator is part of the LIKE prefix so /Archive cannot match
    # /Archive2; SQLAlchemy's autoescape uses "/" as the escape character.
    assert "LIKE" in sql
    assert "ESCAPE '/'" in sql
    values = list(compiled.params.values())
    assert "/Archive" in values
    assert "//Archive//" in values
    assert "/Archive2" in values
    assert "/Arc_hive%x" in values
    # Underscore and percent in a configured root are escaped, not wildcards.
    assert "//Arc/_hive/%x//" in values

