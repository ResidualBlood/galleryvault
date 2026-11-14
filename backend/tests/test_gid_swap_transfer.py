"""T3.1: a gid swap must carry user data over before the old row is deleted.

``finalize_gallery_update`` replaces an old gallery row with the re-uploaded
version.  Every user-owned child table hangs off ``galleries.id`` with
``ON DELETE CASCADE``, so deleting the old row used to wipe reading progress,
history, list membership, series membership and exclusions.  These DB-free tests
pin the ordering (transfer inside the same transaction, before ``delete``), the
``page_count`` precondition, and the PostgreSQL dialect SQL that makes the
transfer clamp + ``GREATEST`` ordering-independent.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from galleryvault.app.state import app_state
from galleryvault.db.models import Gallery, GalleryUpdate
from galleryvault.db.repository import GalleryRepository
from galleryvault.services.updates_worker import finalize_gallery_update

OLD_ID = 10
NEW_ID = 20
OLD_GID = 100
NEW_GID = 200


def _galleries(*, new_page_count: int | None = 5, new_storage_path: str | None = None):
    old_gallery = Gallery(
        id=OLD_ID,
        gid=OLD_GID,
        title="Old",
        storage_path=None,
        storage_type="folder",
        page_count=10,
        local_rating=5,
        local_note="note",
        category="Manga",
    )
    new_gallery = Gallery(
        id=NEW_ID,
        gid=NEW_GID,
        title="New",
        storage_path=new_storage_path,
        storage_type="folder",
        page_count=new_page_count,
        expunged=False,
        trashed=False,
    )
    update_row = GalleryUpdate(
        id=1,
        gallery_id=OLD_ID,
        old_gid=OLD_GID,
        new_gid=NEW_GID,
        new_token="tok",
        title="Title",
        favcat=1,
        status="downloading",
    )
    return old_gallery, new_gallery, update_row


class _FakeSession:
    """Minimal async session recording the order of side effects."""

    def __init__(self, *, old_gallery, new_gallery, update_row):
        self.old_gallery = old_gallery
        self.new_gallery = new_gallery
        self.update_row = update_row
        self.events: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return self

    async def get(self, model, pk):
        if model is Gallery:
            if self.old_gallery.id == pk:
                return self.old_gallery
            if self.new_gallery is not None and self.new_gallery.id == pk:
                return self.new_gallery
            return None
        if model is GalleryUpdate:
            return self.update_row if self.update_row.id == pk else None
        return None

    async def scalar(self, stmt):
        if "gallery_updates" in str(stmt).lower():
            return self.update_row
        return self.new_gallery

    async def delete(self, obj):
        self.events.append(("delete", obj))


def _install(monkeypatch, session):
    monkeypatch.setattr(app_state, "session_factory", lambda: session)


def _spy_transfer(monkeypatch, session):
    calls: list[tuple] = []

    async def fake_transfer(self, *args, **kwargs):
        calls.append((tuple(args), dict(kwargs)))
        session.events.append(("transfer", args))
        return {}

    monkeypatch.setattr(
        GalleryRepository, "transfer_user_data", fake_transfer, raising=False
    )
    return calls


@pytest.mark.asyncio
async def test_finalize_transfers_user_data_before_delete(monkeypatch):
    old_gallery, new_gallery, update_row = _galleries()
    session = _FakeSession(
        old_gallery=old_gallery, new_gallery=new_gallery, update_row=update_row
    )
    _install(monkeypatch, session)
    calls = _spy_transfer(monkeypatch, session)

    ref = SimpleNamespace(id=1, gallery_id=OLD_ID, new_gid=NEW_GID)
    assert await finalize_gallery_update(ref) is None

    assert calls, "finalize must transfer user data before dropping the old row"
    args, _kwargs = calls[0]
    assert args == (OLD_ID, NEW_ID, OLD_GID, NEW_GID)
    assert session.events[0][0] == "transfer"
    assert session.events[-1] == ("delete", old_gallery)
    assert update_row.status == "completed"


@pytest.mark.asyncio
async def test_finalize_postpones_when_new_gallery_has_no_pages(monkeypatch):
    old_gallery, new_gallery, update_row = _galleries(new_page_count=0)
    session = _FakeSession(
        old_gallery=old_gallery, new_gallery=new_gallery, update_row=update_row
    )
    _install(monkeypatch, session)
    calls = _spy_transfer(monkeypatch, session)

    ref = SimpleNamespace(id=1, gallery_id=OLD_ID, new_gid=NEW_GID)
    reason = await finalize_gallery_update(ref)

    assert reason is not None and "page" in reason
    assert calls == []
    assert session.events == []
    assert update_row.status == "downloading"
    assert old_gallery is not None


class _PgDialectSession:
    """Session stub whose bind reports the PostgreSQL dialect (compilation only)."""

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))


def _compile(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_transfer_sql_clamps_progress():
    from galleryvault.db.repositories.galleries_transfer import (
        reading_progress_transfer_stmt,
    )

    stmt = reading_progress_transfer_stmt(
        _PgDialectSession(),
        old_gallery_id=OLD_ID,
        new_gallery_id=NEW_ID,
        new_page_count=5,
    )
    sql = _compile(stmt).upper()

    assert "LEAST(" in sql, "old page must be clamped to the new page count"
    assert "GREATEST(" in sql, "an existing new-version page must not go backwards"
    assert "ON CONFLICT (GALLERY_ID) DO UPDATE" in sql
    assert "INSERT INTO READING_PROGRESS" in sql


def test_transfer_sql_history_keeps_latest_read():
    from galleryvault.db.repositories.galleries_transfer import (
        reading_history_transfer_stmt,
    )

    sql = _compile(
        reading_history_transfer_stmt(
            _PgDialectSession(),
            old_gallery_id=OLD_ID,
            new_gallery_id=NEW_ID,
            new_page_count=5,
        )
    ).upper()

    assert "INSERT INTO READING_HISTORY" in sql
    assert "ON CONFLICT (GALLERY_ID) DO UPDATE" in sql
    assert "GREATEST(" in sql


def test_transfer_sql_series_prefers_manual_source():
    from galleryvault.db.repositories.galleries_transfer import (
        series_items_transfer_stmt,
    )

    sql = _compile(
        series_items_transfer_stmt(
            _PgDialectSession(), old_gallery_id=OLD_ID, new_gallery_id=NEW_ID
        )
    )

    assert "INSERT INTO series_items" in sql
    assert "ON CONFLICT (gallery_id) DO UPDATE" in sql
    # Only an existing ``auto`` row may be overwritten, and only by a ``manual`` one.
    assert "WHERE series_items.source" in sql
    assert "excluded.source" in sql


def test_transfer_sql_online_progress_merges_and_deletes():
    from galleryvault.db.repositories.galleries_transfer import (
        online_progress_delete_stmt,
        online_progress_merge_stmt,
    )

    merge_sql = _compile(
        online_progress_merge_stmt(
            _PgDialectSession(),
            old_gid=OLD_GID,
            new_gid=NEW_GID,
            token="tok",
            title="New",
            thumb="thumb",
            new_page_count=5,
        )
    ).upper()
    delete_sql = _compile(
        online_progress_delete_stmt(_PgDialectSession(), old_gid=OLD_GID)
    ).upper()

    assert "INSERT INTO ONLINE_READING_PROGRESS" in merge_sql
    assert "ON CONFLICT (GID) DO UPDATE" in merge_sql
    assert "LEAST(" in merge_sql and "GREATEST(" in merge_sql
    assert "DELETE FROM ONLINE_READING_PROGRESS" in delete_sql
    assert "GID =" in delete_sql


@pytest.mark.asyncio
async def test_transfer_user_data_is_a_noop_for_missing_old_rows():
    """A transfer on galleries without child rows must not issue any SQL."""

    class _EmptySession:
        def __init__(self):
            self.executed: list[object] = []

        async def get(self, model, pk):
            return None

        async def scalar(self, stmt):
            return None

        async def scalars(self, stmt):
            return SimpleNamespace(all=list)

        async def execute(self, stmt):
            self.executed.append(stmt)

    session = _EmptySession()
    repo = GalleryRepository(session)
    moved = await repo.transfer_user_data(OLD_ID, NEW_ID, OLD_GID, NEW_GID)

    assert session.executed == []
    assert moved == {}
