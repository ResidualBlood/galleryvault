"""T10.1c: non-archive ``galleries.storage_path`` rewrites resync the tier.

DB-free: a fake session is enough to reach the rewrite branches.  Every writer
that moves a row outside the archive flow must leave ``storage_tier``/``cold_at``
consistent with the new path (rule reused from scanner ingest).
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from galleryvault.db.models import DuplicateGroup, Gallery, GalleryMetadata
from galleryvault.scripts.repair_cold_archives import repair_cold_archives
from galleryvault.services import deletion
from galleryvault.services.deletion import delete_galleries_local, delete_local_copy


@pytest.fixture(autouse=True)
def _no_configured_cold_roots(monkeypatch):
    """Pin the runtime archive roots so tier assertions do not depend on env."""
    from galleryvault import storage_paths

    monkeypatch.setattr(storage_paths, "resolve_archive_roots", lambda *a, **k: [])


@pytest.fixture(autouse=True)
def _scan_roots_isolated(monkeypatch, tmp_path):
    """Point get_scan_roots at tmp_path so the deletion boundary check passes."""
    from galleryvault.app import dependencies

    monkeypatch.setattr(dependencies, "get_scan_roots", lambda: [str(tmp_path)])
    return str(tmp_path)


def _deletion_session(gallery_rows, dup_rows):
    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class Session:
        def __init__(self):
            self.dups = dict(dup_rows)
            self.deleted_galleries = []

        async def get(self, model, pk):
            if model is DuplicateGroup:
                return self.dups.get(int(pk))
            return None

        async def scalars(self, statement):
            if "duplicate_groups" in str(statement):
                return _Result(list(self.dups.values()))
            return _Result([])

        async def delete(self, model):
            if isinstance(model, Gallery):
                self.deleted_galleries.append(model.id)

        async def flush(self):
            pass

    return Session()


@pytest.mark.asyncio
async def test_partial_delete_recovery_resyncs_tier_to_surviving_copy(tmp_path, monkeypatch):
    """A failed multi-copy delete keeps the row and re-tiers the surviving copy."""
    ok = tmp_path / "ok-tier"
    bad = tmp_path / "bad-tier"
    ok.mkdir()
    bad.mkdir()
    (bad / "locked").write_bytes(b"x")
    old_cold_at = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    gallery = Gallery(
        id=71,
        gid=7171,
        title="g7171",
        storage_path=str(ok),
        storage_type="dir",
        storage_tier="cold",
        cold_at=old_cold_at,
    )
    dup = DuplicateGroup(
        id=7171,
        kind="same_gid",
        group_key="7171",
        status="open",
        member_gids=[7171],
        payload={
            "policy": "keep_first",
            "winner_path": str(ok),
            "copies": [{"path": str(ok)}, {"path": str(bad)}],
        },
    )

    real = delete_local_copy

    def flaky(path, scan_roots=None):
        return False if Path(path) == bad else real(path, scan_roots)

    monkeypatch.setattr(deletion, "delete_local_copy", flaky)
    results = await delete_galleries_local(
        _deletion_session([gallery], {7171: dup}),
        [gallery],
        delete_files=True,
        delete_all_copies=True,
    )

    assert results[0]["db_removed"] is False
    assert gallery.storage_path == str(bad)
    # The surviving copy is outside the cold root: the tier must follow it.
    assert gallery.storage_tier == "hot"
    assert gallery.cold_at is None


class _RepairSession:
    """Minimal session for ``repair_cold_archives`` (no ``scalars`` => no dup work)."""

    def __init__(self, galleries: list[Gallery], metadata: list[GalleryMetadata] | None = None):
        self.galleries = {g.id: g for g in galleries}
        self.metadata = {m.gid: m for m in (metadata or [])}
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def execute(self, query):
        data = (
            list(self.metadata.values())
            if "from gallery_metadata" in str(query).lower()
            else list(self.galleries.values())
        )

        class _Result:
            def __init__(self, items):
                self.items = items

            def scalars(self):
                return self

            def all(self):
                return self.items

        return _Result(data)

    async def get(self, model, ident):
        if model is GalleryMetadata:
            return self.metadata.get(ident)
        if model is Gallery:
            return self.galleries.get(ident)
        return None

    def add(self, instance):
        if isinstance(instance, Gallery):
            self.galleries[instance.id] = instance

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_repair_cold_rename_marks_tier_cold(tmp_path):
    """Renaming an archived CBZ keeps a cold path out of the hot tier."""
    cold_root = tmp_path / "cold"
    cbz_dir = cold_root / "cbz" / "12" / "34"
    cbz_dir.mkdir(parents=True)

    gid = 12345
    source = cbz_dir / f"{gid}-{gid}-Clean Title.cbz"
    source.write_bytes(b"content")
    gallery = Gallery(
        id=81,
        gid=gid,
        token="tok_81",  # gitleaks:allow
        title="Clean Title",
        title_jpn="Clean Title",
        storage_type="cbz",
        storage_path=str(source),
        storage_tier="hot",
        cold_at=None,
    )

    session = _RepairSession([gallery])
    summary = await repair_cold_archives(
        lambda: session,
        execute=True,
        cold_root_override=cold_root,
        fix_titles=False,
    )

    assert summary["repaired"] == 1
    assert not source.exists()
    assert Path(gallery.storage_path).name == f"{gid}-Clean Title.cbz"
    assert gallery.storage_tier == "cold"
    assert isinstance(gallery.cold_at, datetime)
    assert gallery.cold_at.tzinfo is not None


@pytest.mark.asyncio
async def test_repair_cold_rename_keeps_existing_cold_at(tmp_path):
    """A rename inside the cold root keeps the original archive timestamp."""
    cold_root = tmp_path / "cold"
    cbz_dir = cold_root / "cbz" / "aa" / "bb"
    cbz_dir.mkdir(parents=True)

    gid = 23456
    source = cbz_dir / f"{gid}-{gid}-Keep Stamp.cbz"
    source.write_bytes(b"content")
    old_cold_at = datetime(2023, 5, 6, 7, 8, 9, tzinfo=UTC)
    gallery = Gallery(
        id=82,
        gid=gid,
        token="tok_82",  # gitleaks:allow
        title="Keep Stamp",
        title_jpn="Keep Stamp",
        storage_type="cbz",
        storage_path=str(source),
        storage_tier="cold",
        cold_at=old_cold_at,
    )

    session = _RepairSession([gallery])
    summary = await repair_cold_archives(
        lambda: session,
        execute=True,
        cold_root_override=cold_root,
        fix_titles=False,
    )

    assert summary["repaired"] == 1
    assert Path(gallery.storage_path).name == f"{gid}-Keep Stamp.cbz"
    assert gallery.storage_tier == "cold"
    assert gallery.cold_at == old_cold_at


@pytest.mark.asyncio
async def test_repair_local_rename_clears_cold_tier(tmp_path):
    """Repairing a local name on a stale cold row flips it back to hot."""
    downloads_root = tmp_path / "downloads"
    downloads_root.mkdir()

    gid = 34567
    dirty_dir = downloads_root / f"{gid}-{gid}-Local Title"
    dirty_dir.mkdir()
    (dirty_dir / "001.jpg").write_bytes(b"image")
    gallery = Gallery(
        id=83,
        gid=gid,
        title="Local Title",
        title_jpn="Local Title",
        storage_type="dir",
        storage_path=str(dirty_dir),
        storage_tier="cold",
        cold_at=datetime(2022, 2, 2, 2, 2, 2, tzinfo=UTC),
    )

    session = _RepairSession([gallery])
    summary = await repair_cold_archives(
        lambda: session,
        execute=True,
        fix_titles=False,
        fix_local=True,
    )

    assert summary["local_repaired"] == 1
    assert not dirty_dir.exists()
    assert Path(gallery.storage_path).name == f"{gid}-Local Title"
    assert gallery.storage_tier == "hot"
    assert gallery.cold_at is None
