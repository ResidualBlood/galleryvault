"""Regression tests for the id/gid namespace-collision fix.

A gallery row has both a primary key ``id`` and an ExHentai ``gid``, and the
identifier lookups accept either.  When one gallery's ``id`` numerically
equals another gallery's ``gid``, the old ``or_(id==X, gid==X)`` +
``scalar_one_or_none()`` query raised ``MultipleResultsFound`` → HTTP 500.
The lookups now query ``id`` first and fall back to ``gid`` only on a miss.
"""

from galleryvault.db.models import Gallery
from galleryvault.db.repository import GalleryRepository


class _Row:
    def __init__(self, gallery):
        self.gallery = gallery

    def scalar_one_or_none(self):
        return self.gallery


class LookupSession:
    """Fake async session whose ``scalar`` routes on the WHERE clause.

    ``rows`` is ``{identifier: Gallery}`` — the row to return when the query
    matches that identifier.  ``hits`` records which pass each lookup used.
    """

    def __init__(self, rows: dict[int, Gallery]):
        self._by_id: dict[int, Gallery] = {}
        self._by_gid: dict[int, Gallery] = {}
        for gallery in rows.values():
            self._by_id[gallery.id] = gallery
            if gallery.gid is not None:
                self._by_gid[gallery.gid] = gallery
        self.hits: list[str] = []

    async def scalar(self, statement):
        if not hasattr(statement, "compile"):
            return None
        from sqlalchemy.dialects import postgresql

        sql = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        where = sql.split("WHERE", 1)[1] if "WHERE" in sql else sql
        import re

        match = re.search(r"(?:id|gid) = (\d+)", where)
        key = int(match.group(1)) if match else None
        if "galleries.gid" in where:
            self.hits.append("gid")
            return self._by_gid.get(key)
        self.hits.append("id")
        return self._by_id.get(key)


def _gallery(id_, gid, title):
    return Gallery(id=id_, gid=gid, title=title, storage_type="folder", storage_path=f"/x/{id_}")


async def test_get_by_identifier_prefers_id_when_gid_collides():
    """id==another row's gid must resolve by id, not raise MultipleResultsFound."""
    collision = _gallery(id_=42, gid=999, title="id-42")
    other = _gallery(id_=999, gid=7, title="gid-999")
    session = LookupSession({42: collision, 999: other})

    repo = GalleryRepository(session)
    row = await repo.get_by_identifier(42)

    assert row is collision
    assert session.hits == ["id"]


async def test_get_by_identifier_falls_back_to_gid_on_id_miss():
    """A value that is no id but is a gid must still resolve."""
    other = _gallery(id_=999, gid=7, title="gid-7")
    session = LookupSession({999: other})

    repo = GalleryRepository(session)
    row = await repo.get_by_identifier(7)

    assert row is other
    assert session.hits == ["id", "gid"]


async def test_get_by_identifier_miss_returns_none():
    session = LookupSession({})
    repo = GalleryRepository(session)
    assert await repo.get_by_identifier(12345) is None
    assert session.hits == ["id", "gid"]


async def test_get_for_tag_sync_prefers_id_when_gid_collides():
    collision = _gallery(id_=42, gid=999, title="id-42")
    other = _gallery(id_=999, gid=7, title="gid-999")
    session = LookupSession({42: collision, 999: other})

    repo = GalleryRepository(session)
    row = await repo.get_for_tag_sync(42)

    assert row is collision
    assert session.hits == ["id"]


async def test_main_gallery_uses_id_first():
    """_gallery_lookup must resolve id==X over a gid==X collision row."""
    from galleryvault.app.routers.galleries import _gallery_lookup
    from galleryvault.app.state import app_state

    collision = _gallery(id_=42, gid=999, title="id-42")
    other = _gallery(id_=999, gid=7, title="gid-999")

    class Session:
        def __init__(self):
            self._rows = {42: collision, 999: other}
            self.hits: list[str] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def scalar(self, statement):
            from sqlalchemy.dialects import postgresql

            sql = str(
                statement.compile(
                    dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                )
            )
            where = sql.split("WHERE", 1)[1] if "WHERE" in sql else sql
            self.hits.append("gid" if "galleries.gid" in where else "id")
            import re

            match = re.search(r"(?:id|gid) = (\d+)", where)
            key = int(match.group(1)) if match else None
            return self._rows.get(key)

        async def scalars(self, statement):
            class Result:
                def all(self):
                    return []

            return Result()

    session = Session()

    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: session
    try:
        row, _pages = await _gallery_lookup(42)
    finally:
        app_state.session_factory = orig_factory

    assert row is collision
    assert session.hits == ["id"]
