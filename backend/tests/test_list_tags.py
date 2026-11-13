"""Batch 19: list-row tag parsing plus ``tags_limit`` / ``tag_count`` payloads."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from galleryvault.app.routers.eh import _gallery_payload
from galleryvault.app.routers.eh_online import _detail_payload
from galleryvault.db.repositories.galleries_query import GalleryTagMap
from galleryvault.services.eh_client import EhClient, OnlineGalleryDetail
from galleryvault.services.eh_parsers import SearchGallery, parse_search_page

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "eh_online" / "search-list-compact.html"
)

NO_TAG_HTML = """
<html><body>
<table class="itg">
<tr>
  <td class="gl2c"><div class="glthumb"><div><img src="https://ehgt.org/a.jpg"></div></div></td>
  <td class="gl3c glname">
    <a href="https://e-hentai.org/g/999999/deadbeef/"><div class="glink">No Tags Here</div></a>
  </td>
</tr>
</table>
</body></html>
"""


def _fixture_body() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_fixture_rows_read_tags_from_title_attrs() -> None:
    items, _ = parse_search_page(_fixture_body(), "https://e-hentai.org")
    assert [item.gid for item in items] == [4324717, 4323379, 4319161]
    first = items[0]
    assert len(first.tags) == 12
    assert first.tags[0] == {"namespace": "language", "name": "english"}
    # ``title`` carries the full namespace; the abbreviated row text ("f:...",
    # "l:...") must never leak into the parsed value.
    namespaces = {tag["namespace"] for item in items for tag in item.tags}
    assert {"language", "female", "artist", "other"} <= namespaces
    assert not ({"f", "l", "m", "o"} & namespaces)
    assert {"namespace": "female", "name": "urination"} in items[1].tags


def test_row_without_tag_nodes_returns_empty_list() -> None:
    items, _ = parse_search_page(NO_TAG_HTML, "https://e-hentai.org")
    assert len(items) == 1
    assert items[0].tags == []
    assert items[0].posted is None
    assert items[0].uploader is None


def test_posted_and_uploader_parsed_from_list_row() -> None:
    items, _ = parse_search_page(_fixture_body(), "https://e-hentai.org")
    assert items[0].posted == 1794505140  # 2026-11-12 17:39 UTC
    assert items[0].uploader == "SirNrei"
    assert items[1].uploader == "1234kakkakkak"
    assert items[2].posted is not None


def test_search_payload_adds_tags_display_posted_uploader() -> None:
    item = SearchGallery(
        1,
        "tok",
        "Title",
        "https://e-hentai.org/g/1/tok/",
        tags=[
            {"namespace": "language", "name": "english"},
            {"namespace": "artist", "name": "sirnrei"},
        ],
        posted=1794505140,
        uploader="SirNrei",
    )
    payload = _gallery_payload(item)
    assert payload["gid"] == 1
    assert payload["token"] == "tok"
    assert payload["title"] == "Title"
    assert payload["url"] == "https://e-hentai.org/g/1/tok/"
    for field in ("thumb", "category", "pages", "rating"):
        assert field in payload
    assert payload["tags"][0] == {
        "namespace": "language",
        "name": "english",
        "display": "英语",
    }
    # Unknown tag falls back to the original name.
    assert payload["tags"][1]["display"] == "sirnrei"
    assert payload["posted"] == 1794505140
    assert payload["uploader"] == "SirNrei"


def test_detail_payload_tags_gain_display() -> None:
    detail = OnlineGalleryDetail(
        gid=1,
        token="tok",
        title="Title",
        tags=[
            {"namespace": "language", "name": "english"},
            {"namespace": "artist", "name": "sirnrei"},
        ],
    )
    payload = _detail_payload(detail)
    assert payload["tags"][0] == {
        "namespace": "language",
        "name": "english",
        "display": "英语",
    }
    assert payload["tags"][1]["display"] == "sirnrei"


@pytest.mark.asyncio
async def test_search_upstream_one_request_no_gdata() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.params.get("next"):
            return httpx.Response(200, text="<html><body>No hits found</body></html>")
        return httpx.Response(200, text=_fixture_body())

    http = httpx.AsyncClient(
        base_url="https://e-hentai.org",
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    client = EhClient(client=http)
    try:
        result = await client.search_galleries(q="test")
    finally:
        await http.aclose()
    assert len(seen) == 1
    assert "f_search=test" in seen[0]
    assert "api.php" not in seen[0]
    assert len(result.items) == 3
    assert result.items[0].tags


# --------------------------------------------------------------------------- #
# tags_limit / tag_count
# --------------------------------------------------------------------------- #


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _FakeTagSession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return _Rows(self.rows)


def _tag_rows(gallery_id: int, count: int) -> list[tuple[int, str, str]]:
    return [(gallery_id, "female", f"tag{index}") for index in range(count)]


@pytest.mark.asyncio
async def test_repository_tags_limit_and_counts_single_query() -> None:
    from galleryvault.db.repositories.galleries import GalleryRepository

    session = _FakeTagSession(_tag_rows(1, 6) + _tag_rows(2, 2))
    repo = GalleryRepository(session)  # type: ignore[arg-type]

    limited = await repo.tags_for_galleries([1, 2])
    assert isinstance(limited, GalleryTagMap)
    assert len(limited[1]) == 4
    assert limited.counts == {1: 6, 2: 2}
    assert session.calls == 1

    everything = await repo.tags_for_galleries([1, 2], 0)
    assert len(everything[1]) == 6
    assert everything.counts[1] == 6
    assert session.calls == 2

    assert (await repo.tags_for_galleries([])) == {}
    assert session.calls == 2


def _gallery_row(gallery_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=gallery_id,
        gid=1000 + gallery_id,
        token="tok",
        title="Title",
        title_jpn=None,
        storage_type="folder",
        category="manga",
        page_count=10,
        uploader=None,
        posted_at=None,
        file_size=None,
        storage_size=0,
        rating=None,
        favorite=False,
        favorite_category=None,
        reading_progress=None,
        expunged=False,
        image_quality=None,
        local_rating=None,
        local_note=None,
        trashed_at=None,
        storage_path="",
        updated_at=None,
    )


class _GalleryTagRepo:
    def __init__(self, session=None):
        self.calls = 0

    async def tags_for_galleries(self, ids, limit=4):
        self.calls += 1
        result = GalleryTagMap()
        for gallery_id in ids:
            result.counts[gallery_id] = 6
            result[gallery_id] = [("female", f"tag{i}") for i in range(6 if limit == 0 else limit)]
        return result

    async def progress_for_galleries(self, ids):
        return {}

    async def list_page(self, *args, **kwargs):
        return 1, [_gallery_row(1)]

    async def list_trashed(self, page, page_size):
        return 1, [_gallery_row(1)]

    async def list_expunged(self, page, page_size):
        return 1, [_gallery_row(1)]


@pytest.mark.asyncio
async def test_gallery_list_tags_limit_default_zero_and_count(monkeypatch) -> None:
    from galleryvault.app.routers import galleries

    repo = _GalleryTagRepo()

    async def fake_session():
        yield object()

    monkeypatch.setattr(galleries, "get_session", fake_session)
    monkeypatch.setattr(galleries, "GalleryRepository", lambda session: repo)
    monkeypatch.setattr(galleries, "resolve_session", lambda session, fallback_dep: _async(session))

    default = await galleries.list_galleries(tags_limit=None)
    assert len(default["items"][0]["tags"]) == 4
    assert default["items"][0]["tag_count"] == 6

    everything = await galleries.list_galleries(tags_limit=0)
    assert len(everything["items"][0]["tags"]) == 6
    assert everything["items"][0]["tag_count"] == 6


async def _async(value):
    return value


@pytest.mark.asyncio
async def test_trash_and_expunged_tags_limit(monkeypatch) -> None:
    from galleryvault.app.routers import galleries

    repo = _GalleryTagRepo()

    async def fake_session():
        yield object()

    monkeypatch.setattr(galleries, "get_session", fake_session)
    monkeypatch.setattr(galleries, "GalleryRepository", lambda session: repo)
    monkeypatch.setattr(galleries, "resolve_session", lambda session, fallback_dep: _async(session))

    trash = await galleries.list_trash(tags_limit=0)
    assert len(trash["items"][0]["tags"]) == 6
    assert trash["items"][0]["tag_count"] == 6

    expunged = await galleries.list_expunged(tags_limit=None)
    assert len(expunged["items"][0]["tags"]) == 4
    assert expunged["items"][0]["tag_count"] == 6


@pytest.mark.asyncio
async def test_favorites_items_tags_limit_and_count(monkeypatch) -> None:
    from galleryvault.app.routers import favorites as fav_mod

    class FakeFavRepo:
        def __init__(self, session):
            pass

        async def list_items(self, *args, **kwargs):
            item = SimpleNamespace(
                favcat=1,
                gid=1001,
                token="tok",
                url="https://e-hentai.org/g/1001/tok/",
                title="Title",
                file_size=None,
                first_seen_at=None,
                note=None,
                thumb=None,
            )
            gallery = SimpleNamespace(
                id=1,
                title="Title",
                title_jpn=None,
                category="manga",
                page_count=10,
                file_size=None,
                storage_size=0,
            )
            return 1, [(item, gallery)]

    async def fake_session():
        yield object()

    async def fake_metadata(pairs):
        return {}

    monkeypatch.setattr(fav_mod, "get_session", fake_session)
    monkeypatch.setattr(fav_mod, "GalleryRepository", _GalleryTagRepo)
    monkeypatch.setattr(fav_mod, "FavoritesRepository", FakeFavRepo)
    monkeypatch.setattr(fav_mod, "favorites_metadata", fake_metadata)
    monkeypatch.setattr(fav_mod, "resolve_session", lambda session, fallback_dep: _async(session))

    default = await fav_mod.favorite_items(favcat=1, tags_limit=None)
    assert len(default["items"][0]["tags"]) == 4
    assert default["items"][0]["tag_count"] == 6

    everything = await fav_mod.favorite_items(favcat=1, tags_limit=0)
    assert len(everything["items"][0]["tags"]) == 6
    assert everything["items"][0]["tag_count"] == 6


@pytest.mark.asyncio
async def test_series_tags_limit_and_count(monkeypatch) -> None:
    from galleryvault.app.routers import series as series_mod

    class FakeSeriesRepo:
        def __init__(self, session):
            pass

        async def list_paged(self, page, page_size, show_all):
            series_row = SimpleNamespace(
                id=1,
                name="S",
                match_key="s",
                name_manual=True,
                created_at=None,
            )
            member = SimpleNamespace(
                id=1,
                is_local=True,
                gid=1001,
                token="tok",
                title="Title",
                category="manga",
                page_count=10,
                url=None,
            )
            return [(series_row, 1, [member])], 1

        async def get_with_galleries(self, series_id):
            series_row = SimpleNamespace(
                id=1,
                name="S",
                match_key="s",
                name_manual=True,
                created_at=None,
            )
            member = SimpleNamespace(
                id=1,
                is_local=True,
                gid=1001,
                token="tok",
                title="Title",
                category="manga",
                page_count=10,
                url=None,
            )
            return series_row, [member]

    monkeypatch.setattr(series_mod, "SeriesRepository", FakeSeriesRepo)
    monkeypatch.setattr(series_mod, "GalleryRepository", _GalleryTagRepo)
    monkeypatch.setattr(series_mod, "resolve_session", lambda session, fallback_dep: _async(session))
    monkeypatch.setattr(series_mod, "display_title", lambda g: getattr(g, "title", ""))

    default = await series_mod.list_series(tags_limit=None)
    card = default["items"][0]["galleries"][0]
    assert len(card["tags"]) == 4
    assert card["tag_count"] == 6

    everything = await series_mod.get_series(1, tags_limit=0)
    card = everything["galleries"][0]
    assert len(card["tags"]) == 6
    assert card["tag_count"] == 6


@pytest.fixture
def client() -> TestClient:
    from galleryvault.app.main import app
    from galleryvault.app.state import app_state
    from galleryvault.auth import create_session, hash_password

    original = app_state.settings or app.state.settings
    updated = original.model_copy(
        update={
            "auth_secret": "unit-test-secret",
            "auth_password_hash": hash_password("correct horse"),
            "auth_password": None,
        }
    )
    app_state.settings = updated
    app.state.settings = updated
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set(
                "galleryvault_session", create_session("unit-test-secret", 60)
            )
            yield test_client
    finally:
        app_state.settings = original
        app.state.settings = original


def test_tags_limit_above_64_is_422(client: TestClient) -> None:
    for path in (
        "/api/galleries?tags_limit=65",
        "/api/galleries/trash?tags_limit=65",
        "/api/galleries/expunged?tags_limit=65",
        "/api/favorites/0/items?tags_limit=65",
        "/api/series?tags_limit=65",
        "/api/series/1?tags_limit=65",
    ):
        assert client.get(path).status_code == 422, path
