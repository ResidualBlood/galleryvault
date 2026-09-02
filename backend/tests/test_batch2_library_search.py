"""Tests for Batch 2: library multi-criteria sorting, reading status filtering, exclude tags, favorite searching and cookie health."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects import postgresql

from galleryvault.config import Settings
from galleryvault.db.models import Gallery
from galleryvault.db.repositories.favorites import FavoritesRepository
from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.services.eh_client import probe_cookie_health


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _FakeSession:
    """Fake async session that records compiled SQL for repo queries."""

    def __init__(self, total=1, rows=None):
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


def _gallery(id_, title="Gallery", page_count=20, rating=4.5, file_size=1000):
    now = datetime.now(UTC)
    return Gallery(
        id=id_,
        gid=id_,
        title=title,
        title_jpn=f"{title}_jp",
        storage_type="folder",
        storage_path=f"/x/{id_}",
        page_count=page_count,
        rating=rating,
        file_size=file_size,
        posted_at=now,
        expunged=False,
    )


@pytest.mark.asyncio
async def test_gallery_sorting_and_filtering_sql() -> None:
    rows = [_gallery(1, "Alpha"), _gallery(2, "Beta")]
    session = _FakeSession(total=2, rows=rows)
    repo = GalleryRepository(session)

    # 1. Sort by page_count desc
    await repo.list_page(1, 10, order_by="page_count_desc")
    sql = session.sql[-1].lower()
    assert "order by galleries.page_count desc" in sql

    # 2. Sort by rating desc
    await repo.list_page(1, 10, order_by="rating_desc")
    sql = session.sql[-1].lower()
    assert "order by galleries.rating desc" in sql

    # 3. Sort by title asc
    await repo.list_page(1, 10, order_by="title_asc")
    sql = session.sql[-1].lower()
    assert "order by galleries.title asc" in sql

    # 4. Filter reading status: unread
    await repo.list_page(1, 10, read_status="unread")
    sql = session.sql[-1].lower()
    assert "reading_progress" in sql and ("not exists" in sql or "not (exists" in sql)

    # 5. Filter reading status: reading
    await repo.list_page(1, 10, read_status="reading")
    sql = session.sql[-1].lower()
    assert "reading_progress" in sql and "exists" in sql

    # 6. Filter reading status: completed
    await repo.list_page(1, 10, read_status="completed")
    sql = session.sql[-1].lower()
    assert "reading_progress" in sql and "current_page >=" in sql

    # 7. Exclude tag
    await repo.list_page(1, 10, exclude_tags=[("parody", "fate")])
    sql = session.sql[-1].lower()
    assert "gallery_tags" in sql and ("not exists" in sql or "not (exists" in sql)


@pytest.mark.asyncio
async def test_favorite_repo_search_and_sort_sql() -> None:
    session = _FakeSession(total=1, rows=[])
    fav_repo = FavoritesRepository(session)

    # In-folder keyword search
    await fav_repo.list_items(favcat=2, page=1, page_size=10, q="Archive")
    sql = session.sql[-1].lower()
    assert "%archive%" in sql
    assert "favorite_items.title ilike" in sql

    # In-folder sort by title asc
    await fav_repo.list_items(favcat=2, page=1, page_size=10, order_by="title_asc")
    sql = session.sql[-1].lower()
    assert "order by favorite_items.title asc" in sql

    # In-folder sort by file size desc
    await fav_repo.list_items(favcat=2, page=1, page_size=10, order_by="file_size_desc")
    sql = session.sql[-1].lower()
    assert "order by coalesce(galleries.file_size, favorite_items.file_size) desc" in sql


@pytest.mark.asyncio
async def test_probe_cookie_health() -> None:
    from galleryvault.app.state import app_state

    # When cookies not configured
    app_state.settings = Settings(exhentai_cookies={})
    res = await probe_cookie_health()
    assert res["state"] == "not_configured"

    # When client check_login succeeds
    class DummyEhClient:
        async def check_login(self):
            return "ok", "HTTP 200"

    app_state.settings = Settings(exhentai_cookies={"ipb_member_id": "123", "ipb_pass_hash": "abc"})
    app_state.eh_client = DummyEhClient()
    res = await probe_cookie_health()
    assert res["state"] == "ok"
