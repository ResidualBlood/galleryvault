"""Multi-word free-text search semantics for ``GalleryRepository.list_page``.

A free-form query like ``mimu gif`` must AND the words as independent
substrings (any title containing both words anywhere matches), not treat the
whole string as one contiguous pattern.  Regression: searching two words that
occur in a title but are not adjacent returned nothing.
"""

from sqlalchemy.dialects import postgresql

from galleryvault.db.models import Gallery
from galleryvault.db.repository import GalleryRepository


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _ListPageSession:
    """Fake async session that records the compiled SQL for list_page."""

    def __init__(self, total, rows):
        self.total = total
        self.rows = rows
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


def _gallery(id_, title):
    return Gallery(id=id_, gid=id_, title=title, storage_type="folder", storage_path=f"/x/{id_}")


async def _list_sql(total, rows, q) -> str:
    session = _ListPageSession(total, rows)
    repo = GalleryRepository(session)
    total_out, rows_out = await repo.list_page(1, 24, q=q)
    assert total_out == total and rows_out == rows
    return session.sql[-1]


async def test_list_page_multi_word_ands_tokens_as_substrings():
    rows = [_gallery(1, "MIMU and GIF fanbook")]
    sql = await _list_sql(1, rows, q="mimu gif")
    lowered = sql.lower()
    assert "%mimu%" in lowered and "%gif%" in lowered
    assert "%mimu gif%" not in lowered
    # 2 tokens × (title ILIKE + title_jpn ILIKE) = 4 ILIKE predicates.
    assert lowered.count("ilike") == 4


async def test_list_page_multi_word_three_tokens():
    rows = [_gallery(1, "mimu gif deluxe")]
    sql = await _list_sql(1, rows, q="mimu gif deluxe")
    assert sql.lower().count("ilike") == 6


async def test_list_page_single_token_stays_substring():
    rows = [_gallery(1, "動画")]
    sql = await _list_sql(1, rows, q="動画")
    assert "%動画%" in sql.lower()
    assert sql.lower().count("ilike") == 2


async def test_list_page_no_query_has_no_ilike():
    rows = [_gallery(1, "anything")]
    sql = await _list_sql(1, rows, q="")
    assert "ilike" not in sql.lower()


async def test_list_page_exclude_favorited_adds_not_in_subquery():
    rows = [_gallery(1, "anything")]
    session = _ListPageSession(1, rows)
    repo = GalleryRepository(session)
    await repo.list_page(1, 24, q="", exclude_favorited=True)
    sql = session.sql[-1].lower()
    assert "favorite_items" in sql and ("not in" in sql or "exists" in sql)


async def test_list_page_without_exclude_favorited_has_no_favorites_filter():
    rows = [_gallery(1, "anything")]
    session = _ListPageSession(1, rows)
    repo = GalleryRepository(session)
    await repo.list_page(1, 24, q="")
    assert "favorite_items" not in session.sql[-1].lower()


async def test_list_page_wildcards_escaped():
    from galleryvault.db.repository import escape_like_wildcards

    assert escape_like_wildcards("100%_match\\test") == "100\\%\\_match\\\\test"

    rows = [_gallery(1, "100%_match")]
    sql = await _list_sql(1, rows, q="100%_match")
    # % and _ in the user token must be escaped so they are not treated as SQL wildcards
    assert "100" in sql and "\\_match" in sql


async def test_list_page_exact_tag_uses_tag_id_exists():
    rows = [_gallery(1, "title")]
    session = _ListPageSession(1, rows)
    repo = GalleryRepository(session)
    await repo.list_page(
        1,
        24,
        tags=[("language", "chinese")],
        tag_id_map={("language", "chinese"): 42},
    )
    sql = session.sql[-1].lower()
    assert "gallery_tags.tag_id = 42" in sql
    assert "exists" in sql
    assert "ilike" not in sql


async def test_list_page_multi_exact_tags_and_mode():
    rows = [_gallery(1, "title")]
    session = _ListPageSession(1, rows)
    repo = GalleryRepository(session)
    await repo.list_page(
        1,
        24,
        tags=[("language", "chinese"), ("female", "maid")],
        tag_mode="and",
        tag_id_map={("language", "chinese"): 42, ("female", "maid"): 99},
    )
    sql = session.sql[-1].lower()
    assert "gallery_tags.tag_id = 42" in sql
    assert "gallery_tags.tag_id = 99" in sql
    assert "ilike" not in sql


async def test_list_page_multi_exact_tags_or_mode():
    rows = [_gallery(1, "title")]
    session = _ListPageSession(1, rows)
    repo = GalleryRepository(session)
    await repo.list_page(
        1,
        24,
        tags=[("language", "chinese"), ("female", "maid")],
        tag_mode="or",
        tag_id_map={("language", "chinese"): 42, ("female", "maid"): 99},
    )
    sql = session.sql[-1].lower()
    assert " or " in sql
    assert "gallery_tags.tag_id = 42" in sql
    assert "gallery_tags.tag_id = 99" in sql


async def test_list_page_mixed_exact_and_fuzzy_tags():
    rows = [_gallery(1, "title")]
    session = _ListPageSession(1, rows)
    repo = GalleryRepository(session)
    await repo.list_page(
        1,
        24,
        tags=[("language", "chinese"), (None, "maid")],
        tag_mode="and",
        tag_id_map={("language", "chinese"): 42},
    )
    sql = session.sql[-1].lower()
    assert "gallery_tags.tag_id = 42" in sql
    assert "ilike" in sql


async def test_list_page_exclude_exact_tag():
    rows = [_gallery(1, "title")]
    session = _ListPageSession(1, rows)
    repo = GalleryRepository(session)
    await repo.list_page(
        1,
        24,
        exclude_tags=[("parody", "touhou")],
        tag_id_map={("parody", "touhou"): 77},
    )
    sql = session.sql[-1].lower()
    assert "gallery_tags.tag_id = 77" in sql
    assert "not (exists" in sql or "not exists" in sql
    assert "ilike" not in sql


async def test_resolve_exact_tags_with_mock_session():
    class _MockTagSession:
        def __init__(self, exact_rows, lower_rows_map):
            self.exact_rows = exact_rows
            self.lower_rows_map = lower_rows_map

        async def execute(self, stmt):
            return _Rows(self.exact_rows)

        async def scalars(self, stmt):
            # for unresolved lower query, return simulated matches
            return _Rows(self.lower_rows_map.get("unresolved", []))

    # Case 1: exact match finds (language, chinese) -> 42
    # Case 2: (female, Maid) is unresolved by exact, lower lookup finds [99] -> 99
    # Case 3: (female, ambiguous) finds [1, 2] -> not resolved (fallback ILIKE)
    session = _MockTagSession(
        exact_rows=[(42, "language", "chinese")],
        lower_rows_map={"unresolved": [99]},
    )
    repo = GalleryRepository(session)
    resolved = await repo.resolve_exact_tags([
        ("language", "chinese"),
        ("female", "Maid"),
        (None, "no_ns"),
    ])
    assert resolved == {
        ("language", "chinese"): 42,
        ("female", "Maid"): 99,
    }

