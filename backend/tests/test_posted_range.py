"""T1.4: date-only ``posted_to`` filters include the whole end day (UTC)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects import postgresql

from galleryvault.app.routers.galleries import _parse_posted
from galleryvault.db.repositories.favorites import FavoritesRepository
from galleryvault.db.repositories.galleries import GalleryRepository


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _FakeSession:
    """Fake async session that records compiled PostgreSQL SQL."""

    def __init__(self, total=0, rows=None):
        self.total = total
        self.rows = rows or []
        self.sql = []

    def _compile(self, statement) -> str:
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.sql.append(sql)
        return sql

    async def scalar(self, statement):
        self._compile(statement)
        return self.total

    async def scalars(self, statement):
        self._compile(statement)
        return _Rows(self.rows)

    async def execute(self, statement):
        self._compile(statement)
        return _Rows(self.rows)


def test_posted_to_date_only_is_next_midnight() -> None:
    assert _parse_posted("2024-05-17", upper=True) == datetime(2024, 5, 18, tzinfo=UTC)


def test_posted_from_date_only_unchanged() -> None:
    assert _parse_posted("2024-05-17") == datetime(2024, 5, 17, tzinfo=UTC)


def test_posted_to_with_time_stays_exact() -> None:
    expected = datetime(2024, 5, 17, 13, 45, tzinfo=UTC)
    assert _parse_posted("2024-05-17 13:45", upper=True) == expected
    assert _parse_posted("2024-05-17T13:45:00Z", upper=True) == expected


@pytest.mark.asyncio
async def test_library_posted_to_date_includes_whole_day() -> None:
    session = _FakeSession()
    repo = GalleryRepository(session)
    await repo.list_page(
        1,
        10,
        posted_from=_parse_posted("2024-05-17"),
        posted_to=_parse_posted("2024-05-17", upper=True),
    )
    sql = session.sql[-1]
    assert "posted_at >= '2024-05-17 00:00:00+00:00'" in sql
    assert "posted_at < '2024-05-18 00:00:00+00:00'" in sql
    assert "posted_at <= '2024-05-18" not in sql


@pytest.mark.asyncio
async def test_favorites_posted_to_date_includes_whole_day() -> None:
    session = _FakeSession()
    repo = FavoritesRepository(session)
    await repo.list_items(
        favcat=2,
        page=1,
        page_size=10,
        posted_to=_parse_posted("2024-05-17", upper=True),
    )
    sql = session.sql[-1]
    assert "posted_at < '2024-05-18 00:00:00+00:00'" in sql
    assert "posted_at <= '2024-05-18" not in sql
