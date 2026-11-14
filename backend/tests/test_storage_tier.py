"""T4.1: explicit ``galleries.storage_tier`` state.

DB-free tests: archive writes ``cold``, ingest derives the tier from the cold
roots, and the startup reconcile fixes historical rows idempotently.
"""

from datetime import UTC, datetime
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
    def __init__(self, rows: list) -> None:
        self.rows = rows
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def scalars(self, stmt):
        return SimpleNamespace(all=lambda: self.rows)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_reconcile_fixes_mismatched_rows(tmp_path: Path) -> None:
    from galleryvault.services.cold_archive import reconcile_storage_tier

    cold_root = tmp_path / "Archive"
    cold_root.mkdir()
    cold_path = cold_root / "cbz" / "aa" / "bb" / "400-Cold.cbz"
    hot_path = tmp_path / "downloads" / "401-Hot"
    cold_path_ok = cold_root / "cbz" / "cc" / "dd" / "402-Cold.cbz"
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    rows = [
        Gallery(
            title="mislabeled hot",
            storage_type="cbz",
            storage_path=str(cold_path),
            path_hash="h1",
            storage_signature="s1",
            storage_tier="hot",
            cold_at=None,
            updated_at=stamp,
        ),
        Gallery(
            title="stale cold",
            storage_type="folder",
            storage_path=str(hot_path),
            path_hash="h2",
            storage_signature="s2",
            storage_tier="cold",
            cold_at=stamp,
            updated_at=stamp,
        ),
        Gallery(
            title="already cold",
            storage_type="cbz",
            storage_path=str(cold_path_ok),
            path_hash="h3",
            storage_signature="s3",
            storage_tier="cold",
            cold_at=stamp,
            updated_at=stamp,
        ),
    ]
    session = _ReconcileSession(rows)

    counts = await reconcile_storage_tier(
        session_factory=lambda: session, archive_roots=[cold_root]
    )

    assert counts == {"checked": 3, "fixed_cold": 1, "fixed_hot": 1, "cold_at_filled": 1}
    assert rows[0].storage_tier == "cold"
    assert rows[0].cold_at == stamp  # backfilled from updated_at
    assert rows[1].storage_tier == "hot"
    assert rows[1].cold_at is None
    assert rows[2].storage_tier == "cold"
    assert rows[2].cold_at == stamp
    assert session.commits == 1

    # Idempotent: the second pass makes no further changes.
    counts_again = await reconcile_storage_tier(
        session_factory=lambda: session, archive_roots=[cold_root]
    )
    assert counts_again == {
        "checked": 3,
        "fixed_cold": 0,
        "fixed_hot": 0,
        "cold_at_filled": 0,
    }
    assert session.commits == 1
