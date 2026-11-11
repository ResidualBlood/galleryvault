"""Guards for gallery-update finalize: never delete the old copy before ingest.

``download_worker`` marks the update download task ``success`` before (and
independently of) ingest.  The finalize path used to trust that status alone, so
a slow or failed ingest let it delete the old Gallery row and its files while
the replacement did not exist.  These tests pin the new precondition: finalize
only runs once the new Gallery exists with a verifiable copy on disk, otherwise
the update stays ``downloading`` and is failed only after a bounded wait.
"""

from types import SimpleNamespace

import pytest

from galleryvault.app.state import app_state
from galleryvault.db.models import Gallery, GalleryUpdate
from galleryvault.services import updates_worker
from galleryvault.services.updates_worker import (
    finalize_gallery_update,
    gallery_updates_finalize_loop,
)

OLD_GID = 100
NEW_GID = 200
WAITING = "waiting for ingest"


class _FakeSession:
    """Minimal async session backing ``finalize_gallery_update``."""

    def __init__(self, *, old_gallery, update_row, new_gallery, deleted):
        self.old_gallery = old_gallery
        self.update_row = update_row
        self.new_gallery = new_gallery
        self.deleted = deleted

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return self

    async def get(self, model, pk):
        if model is Gallery:
            return self.old_gallery if self.old_gallery.id == pk else None
        if model is GalleryUpdate:
            return self.update_row if self.update_row.id == pk else None
        return None

    async def scalar(self, stmt):
        sql = str(stmt).lower()
        if "gallery_updates" in sql:
            return self.update_row
        return self.new_gallery

    async def delete(self, obj):
        self.deleted.append(obj)


def _make_galleries(tmp_path, *, new_dir_exists: bool, new_storage_type: str = "folder"):
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    (old_dir / "001.jpg").write_bytes(b"old page")

    new_dir = tmp_path / "new"
    if new_dir_exists:
        new_dir.mkdir()
        (new_dir / "001.jpg").write_bytes(b"new page")

    old_gallery = Gallery(
        id=10,
        gid=OLD_GID,
        title="Old",
        storage_path=str(old_dir),
        storage_type="folder",
        local_rating=5,
        local_note="note",
        category="Manga",
    )
    new_gallery = Gallery(
        id=20,
        gid=NEW_GID,
        title="New",
        storage_path=str(new_dir),
        storage_type=new_storage_type,
        expunged=False,
        trashed=False,
    )
    update_row = GalleryUpdate(
        id=1,
        gallery_id=10,
        old_gid=OLD_GID,
        new_gid=NEW_GID,
        new_token="tok",
        title="Title",
        favcat=1,
        status="downloading",
    )
    return old_gallery, new_gallery, update_row


def _install(monkeypatch, *, old_gallery, update_row, new_gallery):
    deleted: list[object] = []
    session = _FakeSession(
        old_gallery=old_gallery,
        update_row=update_row,
        new_gallery=new_gallery,
        deleted=deleted,
    )
    monkeypatch.setattr(app_state, "session_factory", lambda: session)
    calls: list[object] = []
    monkeypatch.setattr(
        "galleryvault.services.deletion.delete_local_copy",
        lambda path, *args, **kwargs: calls.append(path) or True,
    )
    return deleted, calls


async def test_finalize_waits_when_new_gallery_not_ingested(tmp_path, monkeypatch):
    """Task success but no Gallery row for the new gid: keep the old copy untouched."""
    old_gallery, _, update_row = _make_galleries(tmp_path, new_dir_exists=True)
    deleted, delete_calls = _install(
        monkeypatch, old_gallery=old_gallery, update_row=update_row, new_gallery=None
    )

    reason = await finalize_gallery_update(
        SimpleNamespace(id=1, gallery_id=10, new_gid=NEW_GID)
    )

    assert reason is not None and WAITING in reason
    assert deleted == []
    assert update_row.status == "downloading"
    assert (update_row.error_message or "").startswith(WAITING)
    assert delete_calls == []
    assert (tmp_path / "old" / "001.jpg").exists()


async def test_finalize_waits_when_new_gallery_files_missing(tmp_path, monkeypatch):
    """A Gallery row without its files on disk is not an ingested replacement."""
    old_gallery, new_gallery, update_row = _make_galleries(
        tmp_path, new_dir_exists=False
    )
    deleted, delete_calls = _install(
        monkeypatch,
        old_gallery=old_gallery,
        update_row=update_row,
        new_gallery=new_gallery,
    )

    reason = await finalize_gallery_update(
        SimpleNamespace(id=1, gallery_id=10, new_gid=NEW_GID)
    )

    assert reason is not None and "files missing" in reason
    assert deleted == []
    assert update_row.status == "downloading"
    assert delete_calls == []
    assert (tmp_path / "old" / "001.jpg").exists()


async def test_finalize_completes_when_new_gallery_ingested(tmp_path, monkeypatch):
    """The existing happy path still removes the old gallery and its files."""
    old_gallery, new_gallery, update_row = _make_galleries(tmp_path, new_dir_exists=True)
    deleted, delete_calls = _install(
        monkeypatch,
        old_gallery=old_gallery,
        update_row=update_row,
        new_gallery=new_gallery,
    )

    reason = await finalize_gallery_update(
        SimpleNamespace(id=1, gallery_id=10, new_gid=NEW_GID)
    )

    assert reason is None
    assert deleted == [old_gallery]
    assert update_row.status == "completed"
    assert update_row.error_message is None
    assert new_gallery.local_rating == 5
    assert new_gallery.local_note == "note"
    assert new_gallery.category == "Manga"
    assert len(delete_calls) == 1


async def test_finalize_allows_cold_archive_copy_without_local_files(tmp_path, monkeypatch):
    """Cold-archived replacements live on a possibly unmounted root: no disk check."""
    old_gallery, new_gallery, update_row = _make_galleries(
        tmp_path, new_dir_exists=False, new_storage_type="cold"
    )
    deleted, _ = _install(
        monkeypatch,
        old_gallery=old_gallery,
        update_row=update_row,
        new_gallery=new_gallery,
    )

    reason = await finalize_gallery_update(
        SimpleNamespace(id=1, gallery_id=10, new_gid=NEW_GID)
    )

    assert reason is None
    assert deleted == [old_gallery]
    assert update_row.status == "completed"


class _LoopRow:
    id = 99
    download_task_id = 555
    new_gid = NEW_GID
    status = "downloading"


class _LoopRepo:
    def __init__(self, marked):
        self.marked = marked

    def __call__(self, session):
        return self

    async def downloading(self):
        return [_LoopRow()]

    async def mark_failed(self, update_id, error):
        self.marked.append((update_id, error))
        return True


class _LoopSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return self

    async def get(self, model, pk):
        return SimpleNamespace(status="success")


def _run_loop(monkeypatch, *, finalize, ticks: int, wait_limit: int):
    marked: list[tuple[int, str | None]] = []
    monkeypatch.setattr(app_state, "session_factory", lambda: _LoopSession())
    monkeypatch.setattr(updates_worker, "GalleryUpdatesRepository", _LoopRepo(marked))
    monkeypatch.setattr(updates_worker, "finalize_gallery_update", finalize)
    monkeypatch.setattr(updates_worker, "FINALIZE_WAIT_LIMIT", wait_limit)
    updates_worker._finalize_wait_counts.clear()

    seen = {"n": 0}

    async def fake_sleep(_delay):
        seen["n"] += 1
        if seen["n"] > ticks:
            raise RuntimeError("stop-loop")

    monkeypatch.setattr(updates_worker.asyncio, "sleep", fake_sleep)
    return marked


async def test_finalize_loop_fails_update_after_wait_limit(monkeypatch):
    """A permanent ingest failure becomes ``failed`` only after the bounded wait."""

    async def never_ingested(_row):
        return f"{WAITING}: new gallery not stored yet"

    marked = _run_loop(monkeypatch, finalize=never_ingested, ticks=2, wait_limit=2)

    with pytest.raises(RuntimeError, match="stop-loop"):
        await gallery_updates_finalize_loop()

    assert len(marked) == 1
    update_id, message = marked[0]
    assert update_id == 99
    assert "gave up waiting for ingest" in (message or "")
    assert "old copy kept" in (message or "")
    assert updates_worker._finalize_wait_counts == {}


async def test_finalize_loop_resets_wait_count_after_success(monkeypatch):
    """A later successful finalize clears the wait counter instead of failing the row."""
    snapshots: list[dict[int, int]] = []

    async def waiting_then_done(_row):
        snapshots.append(dict(updates_worker._finalize_wait_counts))
        return f"{WAITING}: new gallery not stored yet" if len(snapshots) == 1 else None

    marked = _run_loop(monkeypatch, finalize=waiting_then_done, ticks=3, wait_limit=5)

    with pytest.raises(RuntimeError, match="stop-loop"):
        await gallery_updates_finalize_loop()

    assert snapshots == [{}, {99: 1}, {}]
    assert marked == []
    assert updates_worker._finalize_wait_counts == {}
