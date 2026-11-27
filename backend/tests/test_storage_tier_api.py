"""T4.2: cold-library visibility.

DB-free tests for the storage-tier dimension:

* ``GET /api/galleries?storage_tier=hot|cold`` filters in SQL and rejects any
  other value with 422;
* list rows and the detail payload expose ``storage_tier`` / ``cold_at``;
* ``GET /api/system/storage`` aggregates cold rows by ``storage_tier`` instead
  of a single path prefix;
* ``POST /api/galleries/delete-filtered`` accepts the same ``storage_tier``
  filter so "what you see is what gets deleted".
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from galleryvault.app.schemas import FilteredDeleteRequest
from galleryvault.db.repository import GalleryRepository


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _RecordingSession:
    """Fake async session that records the compiled PostgreSQL SQL."""

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
    await GalleryRepository(session).list_page(1, 24, **kwargs)
    assert session.sql, "list_page compiled no SQL"
    return session.sql[-1].lower()


@pytest.mark.asyncio
async def test_list_filters_by_storage_tier() -> None:
    cold_sql = await _list_sql(storage_tier="cold")
    assert "galleries.storage_tier = 'cold'" in cold_sql

    hot_sql = await _list_sql(storage_tier="hot")
    assert "galleries.storage_tier = 'hot'" in hot_sql
    assert "galleries.storage_tier = 'hot'" not in cold_sql

    default_sql = await _list_sql()
    assert "galleries.storage_tier = " not in default_sql


def _row(**overrides):
    values = {
        "id": 7,
        "gid": 700,
        "token": "tok7",
        "title": "Cold Gallery",
        "title_jpn": None,
        "storage_type": "cbz",
        "storage_tier": "cold",
        "cold_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        "storage_path": "/Archive/cbz/aa/bb/7-Cold.cbz",
        "category": "manga",
        "page_count": 12,
        "uploader": "someone",
        "posted_at": None,
        "file_size": 1000,
        "storage_size": 900,
        "rating": 4.5,
        "favorite": False,
        "favorite_category": None,
        "reading_progress": None,
        "expunged": False,
        "image_quality": "original",
        "local_rating": None,
        "local_note": None,
        "tags_synced_at": None,
        "source_meta": {},
        "warnings": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_list_serializes_storage_tier_and_forwards_filter(monkeypatch) -> None:
    from galleryvault.app.routers import galleries as galleries_module

    captured: dict = {}
    row = _row()

    class Repo:
        def __init__(self, session):
            self.session = session

        async def resolve_exact_tags(self, tags):
            return {}

        async def list_page(self, page, page_size, *args, **kwargs):
            captured.update(kwargs)
            return 1, [row]

        async def tags_for_galleries(self, ids, limit=None):
            return {}

        async def progress_for_galleries(self, ids):
            return {}

    monkeypatch.setattr(galleries_module, "GalleryRepository", Repo)

    payload = await galleries_module.list_galleries(
        storage_tier="cold", session=object()
    )

    assert captured["storage_tier"] == "cold"
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["storage_tier"] == "cold"
    assert item["cold_at"] == "2026-01-02T03:04:05+00:00"


@pytest.mark.asyncio
async def test_list_rejects_unknown_tier() -> None:
    from galleryvault.app.routers import galleries as galleries_module

    with pytest.raises(HTTPException) as exc:
        await galleries_module.list_galleries(storage_tier="warm", session=object())
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_detail_serializes_storage_tier_and_cold_at(monkeypatch) -> None:
    from galleryvault.app.routers import galleries as galleries_module
    from galleryvault.app.state import app_state
    from galleryvault.config import Settings

    monkeypatch.setattr(app_state, "settings", Settings(auth_required=False))
    row = _row()
    pages = [
        SimpleNamespace(page_index=1, member_name="0001.jpg", media_type="image/jpeg")
    ]

    async def fake_invoke(identifier, session=None):
        return row, pages

    async def fake_tags(gallery_id, session=None):
        return []

    monkeypatch.setattr(galleries_module, "_invoke_gallery", fake_invoke)
    monkeypatch.setattr(galleries_module, "_gallery_tags", fake_tags)

    payload = await galleries_module.get_gallery(7, session=object())

    assert payload["storage_tier"] == "cold"
    assert payload["cold_at"] == "2026-01-02T03:04:05+00:00"


class _StubRequest:
    def __init__(self, payload: dict | None = None):
        self._payload = payload or {}

    async def json(self):
        return self._payload


def _install_delete_repo(monkeypatch, captured: dict):
    from galleryvault.app.routers import galleries as galleries_module

    class Repo:
        def __init__(self, session):
            self.session = session

        async def resolve_exact_tags(self, tags):
            return {}

        async def list_page(self, page, page_size, *args, **kwargs):
            captured.update(kwargs)
            return 0, []

    monkeypatch.setattr(galleries_module, "GalleryRepository", Repo)
    return galleries_module


@pytest.mark.asyncio
async def test_delete_filtered_accepts_storage_tier_only(monkeypatch) -> None:
    captured: dict = {}
    module = _install_delete_repo(monkeypatch, captured)

    result = await module.delete_galleries_filtered(
        FilteredDeleteRequest(storage_tier="cold"), _StubRequest()
    )

    assert result["matched"] == 0
    assert captured["storage_tier"] == "cold"


@pytest.mark.asyncio
async def test_delete_filtered_rejects_unknown_tier(monkeypatch) -> None:
    captured: dict = {}
    module = _install_delete_repo(monkeypatch, captured)

    with pytest.raises(HTTPException) as exc:
        await module.delete_galleries_filtered(
            FilteredDeleteRequest(storage_tier="warm"), _StubRequest()
        )
    assert exc.value.status_code == 422
    assert "storage_tier" not in captured


class _AggregateSession:
    """Returns one tuple per aggregate statement, recording compiled SQL."""

    def __init__(self) -> None:
        self.sql: list[str] = []

    async def execute(self, statement):
        from sqlalchemy.dialects import postgresql

        sql = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.sql.append(sql)
        payload = (3, 30, 300) if "storage_tier = 'cold'" in sql else (5, 50)

        class _Result:
            def first(self):
                return payload

        return _Result()


@pytest.mark.asyncio
async def test_storage_aggregates_use_tier() -> None:
    from galleryvault.services.storage_usage import _query_storage_aggregates

    session = _AggregateSession()
    counts = await _query_storage_aggregates(session)

    assert counts == (3, 30, 300, 5, 50)
    cold_sql = session.sql[0].lower()
    library_sql = session.sql[1].lower()
    assert "galleries.storage_tier = 'cold'" in cold_sql
    assert "galleries.storage_path" not in cold_sql
    assert "trashed" not in cold_sql  # cold consumption includes trash-listed rows
    assert "galleries.storage_tier != 'cold'" in library_sql
    assert "galleries.trashed is false" in library_sql
