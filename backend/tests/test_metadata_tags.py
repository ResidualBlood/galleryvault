"""Regression tests for apply_metadata_to_galleries wiping tags on empty cache.

When the gdata cache for a gallery has an empty ``tags`` list (stale or
partial response), the old code still ran ``delete(GalleryTag)`` for every
gallery in the batch, destroying the tags that were already synced locally.
The delete is now gated on the gallery actually carrying tags in its cache.
"""

from types import SimpleNamespace

from galleryvault.db.repository import GalleryRepository


class _RowResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class Session:
    def __init__(self, pairs):
        self._pairs = pairs
        self.deleted_statements: list[str] = []
        self.inserted_tags: list[tuple[int, int]] = []

    async def execute(self, statement):
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.sql.expression import Delete, Insert, Select

        if isinstance(statement, Select):
            return _RowResult(self._pairs)
        if isinstance(statement, Insert):
            if getattr(statement.table, "name", "") == "gallery_tags":
                multi = getattr(statement, "_multi_values", None)
                single = getattr(statement, "_values", None)
                rows = multi[0] if multi else ([single] if single else [])
                for row in rows:
                    vals = {col.name: val for col, val in row.items()}
                    self.inserted_tags.append((vals["gallery_id"], vals["tag_id"]))
            return SimpleNamespace(rowcount=0)
        if isinstance(statement, Delete):
            self.deleted_statements.append(
                str(
                    statement.compile(
                        dialect=postgresql.dialect(),
                        compile_kwargs={"literal_binds": True},
                    )
                )
            )
            return SimpleNamespace(rowcount=0)
        self.deleted_statements.append(str(statement))
        return SimpleNamespace(rowcount=0)

    async def scalars(self, statement):
        sql = str(statement).lower()
        if "gallery_metadata" in sql:
            metas = [m for _, m in self._pairs if hasattr(m, "gid")]
            return _RowResult(metas)
        return _RowResult([])

    async def flush(self):
        pass


def _gallery(id_, tags_synced_at=None):
    return SimpleNamespace(
        id=id_,
        gid=id_,
        category=None,
        title=None,
        title_jpn=None,
        uploader=None,
        file_count=None,
        file_size=None,
        rating=None,
        posted_at=None,
        source_meta={},
        tags_synced_at=tags_synced_at,
    )


def _meta(*, tags):
    return SimpleNamespace(
        category="manga",
        title="t",
        title_jpn="tj",
        uploader="u",
        file_count=10,
        file_size=100,
        rating=4.5,
        posted_at=None,
        tags=tags,
    )


async def test_empty_cache_tags_keep_local_tags() -> None:
    """Empty cached tags must not delete the gallery's existing GalleryTags."""
    gallery = _gallery(1, tags_synced_at=None)
    session = Session([(gallery, _meta(tags=None))])

    count = await GalleryRepository(session).apply_metadata_to_galleries(5, limit=10)

    assert count == 1
    # The delete ran for no gallery: local tags are preserved.
    assert session.deleted_statements == []
    assert session.inserted_tags == []
    # The rest of the metadata is still applied.
    assert gallery.category == "manga"
    assert gallery.title == "t"
    assert gallery.title_jpn == "tj"
    assert gallery.file_count == 10


async def test_empty_tags_list_same_as_none() -> None:
    gallery = _gallery(2, tags_synced_at=None)
    session = Session([(gallery, _meta(tags=[]))])

    count = await GalleryRepository(session).apply_metadata_to_galleries(5, limit=10)

    assert count == 1
    assert session.deleted_statements == []
    assert session.inserted_tags == []


async def test_nonempty_cache_tags_still_replaced() -> None:
    """Galleries whose cache really has tags keep the delete+refill behavior."""
    gallery = _gallery(3, tags_synced_at=None)
    session = Session([(gallery, _meta(tags=[["artist", "alice"]]))])

    count = await GalleryRepository(session).apply_metadata_to_galleries(5, limit=10)

    assert count == 1
    assert len(session.deleted_statements) == 1
    # The delete is scoped to the tagged gallery.
    assert "3" in str(session.deleted_statements[0])


async def test_mixed_batch_only_deletes_tagged_galleries() -> None:
    """An untagged gallery in a batch must not lose its local tags."""
    untagged = _gallery(10, tags_synced_at=None)
    tagged = _gallery(11, tags_synced_at=None)
    session = Session([(untagged, _meta(tags=[])), (tagged, _meta(tags=[["artist", "bob"]]))])

    count = await GalleryRepository(session).apply_metadata_to_galleries(5, limit=10)

    assert count == 2
    assert len(session.deleted_statements) == 1
    # Only the tagged gallery's id appears in the DELETE ... IN (...).
    assert "10" not in str(session.deleted_statements[0])
    assert "11" in str(session.deleted_statements[0])


async def test_upsert_metadata_includes_uploader_parent_gid_thumb() -> None:
    """upsert_metadata includes uploader, parent_gid, thumb and detects their changes in WHERE clause."""
    executed_statements = []

    class MockSession:
        async def execute(self, statement):
            executed_statements.append(statement)
            return SimpleNamespace(rowcount=1)

    repo = GalleryRepository(MockSession())
    entries = [
        {
            "gid": 12345,
            "token": "tok12345",
            "title": "Title 12345",
            "uploader": "custom_uploader",
            "parent": "8888",
            "thumb": "https://img.eh/thumb.jpg",
            "file_count": 20,
            "category": "Manga",
            "tags": [["artist", "bob"]],
        }
    ]

    count = await repo.upsert_metadata(entries)
    assert count == 1
    assert len(executed_statements) == 1
    stmt = executed_statements[0]
    from sqlalchemy.dialects import postgresql

    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()
    # Verify columns in INSERT values or ON CONFLICT SET
    assert "parent_gid" in sql
    assert "uploader" in sql
    assert "thumb" in sql
    # Verify values bound
    params = compiled.params
    assert any(v == 8888 for v in params.values())
    assert any(v == "custom_uploader" for v in params.values())
    assert any(v == "https://img.eh/thumb.jpg" for v in params.values())
    # Verify conflict where conditions detect distinct changes
    assert "gallery_metadata.uploader is distinct from" in sql
    assert "gallery_metadata.parent_gid is distinct from" in sql
    assert "gallery_metadata.thumb is distinct from" in sql


async def test_apply_cached_metadata_applies_all_fields_to_galleries() -> None:
    """apply_cached_metadata (and apply_metadata_to_galleries) sets uploader, file_count, parent_gid."""
    gallery = _gallery(99)
    meta = SimpleNamespace(
        gid=99,
        category="Artist CG",
        title="Title 99",
        title_jpn="日本語 99",
        uploader="great_uploader",
        file_count=35,
        file_size=2000000,
        rating=4.7,
        posted_at=None,
        expunged=False,
        parent_gid=54321,
        tags=[["artist", "master"]],
    )
    session = Session([(gallery, meta)])

    # Can apply directly by passing galleries sequence
    count = await GalleryRepository(session).apply_cached_metadata(galleries=[gallery])
    assert count == 1
    assert gallery.category == "Artist CG"
    assert gallery.title == "Title 99"
    assert gallery.title_jpn == "日本語 99"
    assert gallery.uploader == "great_uploader"
    assert gallery.file_count == 35
    assert gallery.rating == 4.7
    assert gallery.source_meta.get("parent_gid") == 54321

