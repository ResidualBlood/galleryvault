"""Regression tests for ``POST /api/galleries/delete-filtered`` filter fidelity.

P0: the endpoint counted ``favorite``/``read``/``expunged``/``media_type``/
``storage_type`` towards ``has_filters`` but never forwarded them to
``GalleryRepository.list_page``.  A body such as ``{"expunged": false}`` was
therefore accepted as "filtered" while the SQL matched the whole library and
deleted everything (45/45 observed live).

Two invariants are covered here:

1. the five filters are forwarded to ``list_page`` and compiled into SQL, so
   the delete set equals the browse set;
2. a delete matching more than 200 galleries needs an explicit
   ``confirm`` + ``match_count`` echo (409 otherwise).
"""

import pytest

from galleryvault.app.schemas import FilteredDeleteRequest
from galleryvault.db.models import Gallery
from galleryvault.db.repository import GalleryRepository


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _RecordingSession:
    """Fake async session that records the compiled SQL of ``list_page``."""

    def __init__(self, total=0, rows=()):
        self.total = total
        self.rows = list(rows)
        self.sql: list[str] = []

    def _compile(self, statement) -> str:
        from sqlalchemy.dialects import postgresql

        compiled = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.sql.append(compiled)
        return compiled

    async def scalar(self, statement):
        self._compile(statement)
        return self.total

    async def scalars(self, statement):
        self._compile(statement)
        return _Rows(self.rows)

    async def execute(self, statement):
        self._compile(statement)
        return _Rows(self.rows)


async def _list_sql(**kwargs) -> str:
    session = _RecordingSession()
    repo = GalleryRepository(session)
    await repo.list_page(1, 24, **kwargs)
    assert session.sql, "list_page compiled no SQL"
    return session.sql[-1].lower()


class _StubRequest:
    """Minimal ``Request`` stand-in exposing only the JSON guard fields."""

    def __init__(self, payload: dict | None = None):
        self._payload = payload or {}

    async def json(self):
        return self._payload


async def test_list_page_favorite_true_only_matches_favorites():
    favorited = await _list_sql(favorite=True)
    # The favorite flag is derived from favorite_items / gallery_updates rows,
    # and un-favorited galleries (gid IS NULL) can never match.
    assert "favorite_items" in favorited
    assert "gallery_updates" in favorited
    assert "exists" in favorited
    assert "galleries.gid is not null" in favorited

    not_favorited = await _list_sql(favorite=False)
    assert not_favorited != favorited
    assert "not (" in not_favorited or "not exists" in not_favorited

    default_sql = await _list_sql()
    assert default_sql != favorited
    assert "favorite_items" not in default_sql


async def test_list_page_read_filter_uses_reading_progress():
    read_sql = await _list_sql(read=True)
    unread_sql = await _list_sql(read=False)
    assert "reading_progress" in read_sql
    assert "reading_progress" in unread_sql
    assert read_sql != unread_sql
    assert "not (" in unread_sql or "not exists" in unread_sql


async def test_list_page_expunged_filter_switches_predicate():
    hidden = await _list_sql(expunged=False)
    shown = await _list_sql(expunged=True)
    default_sql = await _list_sql()
    assert "galleries.expunged is false" in hidden
    assert "galleries.expunged is true" in shown
    assert "galleries.expunged is true" not in hidden
    # omitting the flag keeps the old "hide expunged" default
    assert "galleries.expunged is false" in default_sql


async def test_list_page_media_type_and_storage_type_filters():
    sql = await _list_sql(media_type="gif", storage_type="folder")
    assert "gallery_pages.media_type = 'gif'" in sql
    assert "galleries.storage_type = 'folder'" in sql
    default_sql = await _list_sql()
    assert "gallery_pages.media_type" not in default_sql
    assert "galleries.storage_type = " not in default_sql


def _install_repo(monkeypatch, rows, captured: dict | None = None):
    from galleryvault.app.routers import galleries as galleries_module

    class Repo:
        def __init__(self, session):
            self.session = session

        async def resolve_exact_tags(self, tags):
            return {}

        async def list_page(self, page, page_size, *args, **kwargs):
            if captured is not None:
                captured.update(kwargs)
            start = (page - 1) * page_size
            return len(rows), rows[start : start + page_size]

    monkeypatch.setattr(galleries_module, "GalleryRepository", Repo)
    return galleries_module


@pytest.fixture
def _delete_setup(monkeypatch):
    """Install an in-memory session factory plus a recording delete stub."""
    from galleryvault.app.state import app_state as state

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def begin(self):
            return self

        async def scalars(self, statement):
            return _Rows([])

    orig_factory = state.session_factory
    state.session_factory = lambda: Session()
    deleted_batches: list[int] = []
    yield deleted_batches
    state.session_factory = orig_factory


def _patch_delete(monkeypatch, module, batches: list[int]):
    async def fake_delete(batch, *args, delete_files=False, delete_all_copies=False, **kw):
        actual = args[0] if args else batch
        batches.append(len(actual))
        return [
            {
                "gallery_id": g if isinstance(g, int) else g.id,
                "gid": getattr(g, "gid", None),
                "db_removed": True,
                "deleted_paths": [],
                "failed_paths": [],
            }
            for g in actual
        ]

    monkeypatch.setattr(module, "delete_galleries_local", fake_delete)


@pytest.mark.asyncio
async def test_delete_filtered_forwards_favorite_read_expunged_media_storage(
    monkeypatch, _delete_setup
):
    from galleryvault.app.routers.galleries import delete_galleries_filtered

    captured: dict = {}
    module = _install_repo(monkeypatch, [], captured)
    _patch_delete(monkeypatch, module, _delete_setup)

    body = FilteredDeleteRequest(
        favorite=True,
        read=False,
        expunged=True,
        media_type="gif",
        storage_type="folder",
    )
    result = await delete_galleries_filtered(body, _StubRequest())

    assert result["matched"] == 0
    assert captured["favorite"] is True
    assert captured["read"] is False
    assert captured["expunged"] is True
    assert captured["media_type"] == "gif"
    assert captured["storage_type"] == "folder"


@pytest.mark.asyncio
async def test_delete_filtered_expunged_false_alone_is_forwarded(monkeypatch, _delete_setup):
    """``{"expunged": false}`` must reach list_page instead of hitting all rows."""
    from galleryvault.app.routers.galleries import delete_galleries_filtered

    captured: dict = {}
    module = _install_repo(monkeypatch, [], captured)
    _patch_delete(monkeypatch, module, _delete_setup)

    body = FilteredDeleteRequest(expunged=False)
    result = await delete_galleries_filtered(body, _StubRequest())

    assert result["matched"] == 0
    assert captured["expunged"] is False
    assert captured["favorite"] is None


@pytest.mark.asyncio
async def test_delete_filtered_empty_filter_still_rejected(monkeypatch, _delete_setup):
    from fastapi import HTTPException

    from galleryvault.app.routers.galleries import delete_galleries_filtered

    module = _install_repo(monkeypatch, [])
    _patch_delete(monkeypatch, module, _delete_setup)

    with pytest.raises(HTTPException) as excinfo:
        await delete_galleries_filtered(FilteredDeleteRequest(q="  "), _StubRequest())
    assert excinfo.value.status_code == 400


def _rows(count: int) -> list[Gallery]:
    return [Gallery(id=i, gid=5000 + i, title=f"g{i}", storage_path="") for i in range(1, count + 1)]


@pytest.mark.asyncio
async def test_delete_filtered_above_threshold_requires_confirm(monkeypatch, _delete_setup):
    from fastapi import HTTPException

    from galleryvault.app.routers.galleries import delete_galleries_filtered

    module = _install_repo(monkeypatch, _rows(250))
    _patch_delete(monkeypatch, module, _delete_setup)

    body = FilteredDeleteRequest(favorite=True)
    with pytest.raises(HTTPException) as excinfo:
        await delete_galleries_filtered(body, _StubRequest())
    assert excinfo.value.status_code == 409
    detail = excinfo.value.detail
    assert detail["code"] == "CONFIRM_REQUIRED"
    assert detail["matched"] == 250
    assert "confirm" in detail["message"]
    assert _delete_setup == []  # nothing was deleted


@pytest.mark.asyncio
async def test_delete_filtered_confirm_with_stale_match_count_rejected(monkeypatch, _delete_setup):
    from fastapi import HTTPException

    from galleryvault.app.routers.galleries import delete_galleries_filtered

    module = _install_repo(monkeypatch, _rows(250))
    _patch_delete(monkeypatch, module, _delete_setup)

    body = FilteredDeleteRequest(favorite=True)
    with pytest.raises(HTTPException) as excinfo:
        await delete_galleries_filtered(
            body, _StubRequest({"confirm": True, "match_count": 240})
        )
    assert excinfo.value.status_code == 409
    assert "match_count" in excinfo.value.detail
    assert _delete_setup == []


@pytest.mark.asyncio
async def test_delete_filtered_confirm_with_matching_count_deletes(monkeypatch, _delete_setup):
    from galleryvault.app.routers.galleries import delete_galleries_filtered

    module = _install_repo(monkeypatch, _rows(250))
    _patch_delete(monkeypatch, module, _delete_setup)

    body = FilteredDeleteRequest(favorite=True)
    result = await delete_galleries_filtered(
        body, _StubRequest({"confirm": True, "match_count": 250})
    )
    assert result["matched"] == 250
    assert result["deleted"] == 250
    assert _delete_setup == [250]


@pytest.mark.asyncio
async def test_delete_filtered_small_match_needs_no_confirm(monkeypatch, _delete_setup):
    from galleryvault.app.routers.galleries import delete_galleries_filtered

    module = _install_repo(monkeypatch, _rows(2))
    _patch_delete(monkeypatch, module, _delete_setup)

    body = FilteredDeleteRequest(favorite=True)
    result = await delete_galleries_filtered(body, _StubRequest())
    assert result["matched"] == 2
    assert _delete_setup == [2]
