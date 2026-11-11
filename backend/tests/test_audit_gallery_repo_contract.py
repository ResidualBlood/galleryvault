"""T6 audit fixes: gallery repository contract + atomic reading progress.

Covers the two methods the routers/services already called but the repository
never implemented (``category_counts`` -> 500 on ``/api/galleries/categories``,
``get_by_gid`` -> 500 on identifier lookups) and the read-then-write progress
upsert that could lose the furthest page under concurrent saves.

The PostgreSQL path is asserted by compiling the generated statement; the
monotonic behaviour is executed for real against SQLite (the session shim
below bridges the sync driver the unit-test environment ships).
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from galleryvault.app.routers import galleries as galleries_router
from galleryvault.app.schemas import ProgressRequest
from galleryvault.db.models import Gallery, ReadingHistory, ReadingProgress
from galleryvault.db.repositories.galleries import GalleryRepository

_PG = postgresql.dialect()


def _sql(stmt: object) -> str:
    return str(stmt.compile(dialect=_PG, compile_kwargs={"literal_binds": True})).replace("\n", " ")


# --------------------------------------------------------------------------- #
# contract
# --------------------------------------------------------------------------- #


def test_contract_methods_exist_with_expected_signatures() -> None:
    get_by_gid = getattr(GalleryRepository, "get_by_gid", None)
    category_counts = getattr(GalleryRepository, "category_counts", None)

    assert callable(get_by_gid)
    assert callable(category_counts)
    assert list(inspect.signature(get_by_gid).parameters) == ["self", "gid"]
    assert list(inspect.signature(category_counts).parameters) == ["self"]


class _RowsResult:
    def __init__(self, rows: list[tuple[str, int]]) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _ExecSession:
    def __init__(self, rows: list[tuple[str, int]]) -> None:
        self.rows = rows
        self.stmt: object | None = None

    async def execute(self, stmt: object) -> _RowsResult:
        self.stmt = stmt
        return _RowsResult(self.rows)


async def test_category_counts_returns_pairs_for_live_galleries() -> None:
    session = _ExecSession([("doujinshi", 3), ("manga", 1)])

    counts = await GalleryRepository(session).category_counts()

    assert counts == [("doujinshi", 3), ("manga", 1)]
    sql = _sql(session.stmt)
    assert "FROM galleries" in sql
    assert "galleries.expunged IS false" in sql
    assert "galleries.trashed IS false" in sql
    assert "galleries.category IS NOT NULL" in sql
    assert "GROUP BY galleries.category" in sql


class _ScalarSession:
    def __init__(self, row: Gallery | None) -> None:
        self.row = row
        self.stmt: object | None = None

    async def scalar(self, stmt: object) -> Gallery | None:
        self.stmt = stmt
        return self.row


async def test_get_by_gid_returns_newest_live_row() -> None:
    gallery = Gallery(
        id=9,
        gid=42,
        title="found",
        storage_type="folder",
        storage_path="/library/9",
    )
    session = _ScalarSession(gallery)

    fetched = await GalleryRepository(session).get_by_gid(42)

    assert fetched is gallery
    sql = _sql(session.stmt)
    assert "galleries.gid = 42" in sql
    assert "galleries.expunged IS false" in sql
    assert "galleries.trashed IS false" in sql
    assert "ORDER BY galleries.id DESC" in sql
    assert "LIMIT 1" in sql


async def test_get_by_gid_returns_none_on_miss() -> None:
    assert await GalleryRepository(_ScalarSession(None)).get_by_gid(1234) is None


async def test_list_categories_route_uses_repository_counts(
    monkeypatch,
) -> None:
    class _Repo:
        def __init__(self, _session: object) -> None:
            pass

        async def category_counts(self) -> list[tuple[str, int]]:
            return [("manga", 2)]

    monkeypatch.setattr(galleries_router, "GalleryRepository", _Repo)

    payload = await galleries_router.list_categories(session=object())

    counts = {item["name"]: item["count"] for item in payload["categories"]}
    assert counts["manga"] == 2
    assert counts["doujinshi"] == 0
    assert set(counts) == set(galleries_router.CATEGORIES)


# --------------------------------------------------------------------------- #
# atomic progress / history
# --------------------------------------------------------------------------- #


class _PgBind:
    class dialect:  # plain attribute container
        name = "postgresql"


class _OneResult:
    def __init__(self, row: tuple) -> None:
        self._row = row

    def one(self) -> tuple:
        return self._row


class _PgSession:
    """Fake async session that captures the statement for compilation checks."""

    def __init__(self, row: tuple) -> None:
        self.row = row
        self.stmt: object | None = None

    def get_bind(self) -> _PgBind:
        return _PgBind()

    async def execute(self, stmt: object) -> _OneResult:
        self.stmt = stmt
        return _OneResult(self.row)


async def test_advance_progress_is_one_greatest_upsert() -> None:
    updated = datetime(2026, 1, 2, tzinfo=UTC)
    session = _PgSession((1, 10, 20, updated))

    row, advanced = await GalleryRepository(session).advance_progress(1, 5, 20)

    assert advanced is False
    assert row.current_page == 10
    assert row.total_pages == 20
    sql = _sql(session.stmt).upper()
    assert "INSERT INTO READING_PROGRESS" in sql
    assert "ON CONFLICT (GALLERY_ID) DO UPDATE" in sql
    assert "GREATEST(READING_PROGRESS.CURRENT_PAGE, EXCLUDED.CURRENT_PAGE)" in sql
    assert "RETURNING READING_PROGRESS.GALLERY_ID" in sql


async def test_advance_progress_reports_forward_writes() -> None:
    session = _PgSession((1, 12, 30, datetime(2026, 1, 2, tzinfo=UTC)))

    row, advanced = await GalleryRepository(session).advance_progress(1, 12, 30)

    assert advanced is True
    assert row.current_page == 12
    assert row.total_pages == 30


class _AsyncSessionShim:
    """Async facade over a sync SQLAlchemy session (no aiosqlite in the suite)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_bind(self) -> object:
        return self.session.get_bind()

    async def execute(self, stmt: object) -> object:
        return self.session.execute(stmt)

    async def flush(self) -> None:
        self.session.flush()


def _sqlite_engine():
    engine = create_engine("sqlite://")
    ReadingProgress.__table__.create(engine)
    # ``ReadingHistory.id`` uses an Identity column that SQLite cannot render;
    # the same shape with AUTOINCREMENT is enough to execute the real upsert.
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE reading_history ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "gallery_id INTEGER NOT NULL UNIQUE, "
                "current_page INTEGER NOT NULL DEFAULT 0, "
                "total_pages INTEGER, "
                "last_read_at DATETIME)"
            )
        )
    return engine


async def test_progress_and_history_never_move_backwards() -> None:
    engine = _sqlite_engine()
    session = Session(engine)
    try:
        repo = GalleryRepository(_AsyncSessionShim(session))

        stored, advanced = await repo.advance_progress(1, 10, 20)
        assert advanced is True
        assert stored.current_page == 10

        stale, advanced = await repo.advance_progress(1, 5, 20)
        assert advanced is False
        assert stale.current_page == 10
        assert stale.total_pages == 20
        assert (
            session.execute(
                select(ReadingProgress.current_page).where(ReadingProgress.gallery_id == 1)
            ).scalar_one()
            == 10
        )

        await repo.record_history(1, 10, 20)
        latest = await repo.record_history(1, 4, 20)
        assert latest.current_page == 10
        history = session.execute(select(ReadingHistory)).scalars().all()
        assert len(history) == 1
        assert history[0].current_page == 10
    finally:
        session.close()
        engine.dispose()


async def test_save_progress_mirrors_persisted_page_into_history(monkeypatch) -> None:
    row = SimpleNamespace(id=7, gid=42, token="tok", title="T")
    pages = [
        SimpleNamespace(page_index=i, member_name=f"{i:04d}.jpg", media_type="jpg", manifest={})
        for i in range(10)
    ]
    recorded: list[tuple[int, int, int]] = []

    class _Repo:
        def __init__(self, _session: object) -> None:
            pass

        async def advance_progress(self, gallery_id: int, current: int, total: int):
            # A concurrent request already stored page 9; ours (6) was stale.
            return SimpleNamespace(current_page=9, total_pages=total), True

        async def record_history(self, gallery_id: int, current: int, total: int) -> None:
            recorded.append((gallery_id, current, total))

    async def _lookup(*args: object, **kwargs: object) -> tuple[object, list[object]]:
        return row, pages

    monkeypatch.setattr(galleries_router, "_invoke_gallery", _lookup)
    monkeypatch.setattr(galleries_router, "GalleryRepository", _Repo)

    session = MagicMock()
    session.in_transaction = MagicMock(return_value=False)
    session.commit = MagicMock()

    result = await galleries_router.save_gallery_progress(
        7, ProgressRequest(current_page=6), session=session, gallery_service=None
    )

    assert result["current_page"] == 9
    assert recorded == [(7, 9, 10)]
