"""Batch 3: ExHentai discover search — parse, classify, badges, cache."""

from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException

from galleryvault.app.routers.eh import attach_search_badges, eh_search, parse_category_param
from galleryvault.app.state import app_state
from galleryvault.services.eh_client import (
    EhClient,
    EhSearchResult,
    SearchGallery,
    _usable_thumb_src,
    classify_search_body,
    get_fixed_preview_thumb_url,
    parse_search_page,
)

SEARCH_LIST_HTML = """
<html><body>
<table class="itg gltc">
<tr>
  <td class="gl1c glcat"><div class="cs ct2">Doujinshi</div></td>
  <td class="gl2c">
    <div class="glthumb">
      <div><img src="https://ehgt.org/aa/bb/thumb-alpha.jpg" alt=""></div>
      <div>
        <div>24 pages</div>
        <div class="ir" style="background-position:0px -1px" title="Average: 4.50"></div>
      </div>
    </div>
  </td>
  <td class="gl3c glname">
    <a href="https://exhentai.org/g/111111/aaaaaa/">
      <div class="glink">Alpha Gallery</div>
    </a>
  </td>
</tr>
<tr>
  <td class="gl1c glcat"><div class="cs ct1">Manga</div></td>
  <td class="gl2c">
    <div class="glthumb">
      <div><img src="https://ehgt.org/cc/dd/thumb-beta.jpg" alt=""></div>
      <div>
        <div>36 pages</div>
        <div class="ir" title="Average: 3.25"></div>
      </div>
    </div>
  </td>
  <td class="gl3c glname">
    <a href="https://exhentai.org/g/222222/bbbbbb/">
      <div class="glink">Beta Gallery</div>
    </a>
  </td>
</tr>
</table>
<script>var nexturl="https://exhentai.org/?f_search=test&amp;next=222222-1770000000";</script>
<a id="unext" href="https://exhentai.org/?next=222222-1770000000">&gt;</a>
</body></html>
"""

SEARCH_THUMBNAIL_LAZY_HTML = """
<html><body>
<div class="gl1t">
  <a href="/g/111111/aaaaaa/"><img src="blank.gif" data-src="https://ehgt.org/real.jpg"></a>
  <a href="/g/111111/aaaaaa/"><div class="glink">Lazy Cover</div></a>
  <div>12 pages</div>
</div>
</body></html>
"""

_SXJ_THUMB_LAST = (
    "317a1a254cd9c3269e71b2aa2671fe8d28c91097-260198-640-480-png_250.jpg"
)
_SXJ_THUMB_EHGT = f"https://ehgt.org/31/7a/{_SXJ_THUMB_LAST}"

SEARCH_SXJ_THUMB_HTML = f"""
<html><body>
<table class="itg gltc">
<tr>
  <td class="gl2c"><div class="glthumb"><div>
    <a href="https://exhentai.org/g/111111/aaaaaa/">
      <img src="https://s.exhentai.org/t/31/7a/{_SXJ_THUMB_LAST}" alt="">
    </a>
  </div></div></td>
  <td class="gl3c glname">
    <a href="https://exhentai.org/g/111111/aaaaaa/"><div class="glink">S Host</div></a>
  </td>
</tr>
<tr>
  <td class="gl2c"><div class="glthumb"><div>
    <a href="https://exhentai.org/g/222222/bbbbbb/">
      <img src="https://exhentai.org/t/31/7a/{_SXJ_THUMB_LAST}" alt="">
    </a>
  </div></div></td>
  <td class="gl3c glname">
    <a href="https://exhentai.org/g/222222/bbbbbb/"><div class="glink">T Path</div></a>
  </td>
</tr>
<tr>
  <td class="gl2c"><div class="glthumb"><div>
    <a href="https://exhentai.org/g/333333/cccccc/">
      <img src="https://s.exhentai.org/t/xx/yy/zzzz.jpg" alt="">
    </a>
  </div></div></td>
  <td class="gl3c glname">
    <a href="https://exhentai.org/g/333333/cccccc/"><div class="glink">No Match</div></a>
  </td>
</tr>
</table>
</body></html>
"""


def test_parse_search_page_extracts_rows_and_cursor() -> None:
    items, cursor = parse_search_page(SEARCH_LIST_HTML)
    assert cursor == "222222-1770000000"
    assert [it.gid for it in items] == [111111, 222222]
    assert items[0].token == "aaaaaa"
    assert items[0].title == "Alpha Gallery"
    assert items[0].thumb == "https://ehgt.org/aa/bb/thumb-alpha.jpg"
    assert items[0].category == "doujinshi"
    assert items[0].pages == 24
    assert items[0].rating == 4.5
    assert items[1].title == "Beta Gallery"
    assert items[1].category == "manga"
    assert items[1].pages == 36
    assert items[1].rating == 3.25


def test_parse_search_page_prefers_data_src_over_blank_gif() -> None:
    items, _ = parse_search_page(SEARCH_THUMBNAIL_LAZY_HTML)
    assert [it.gid for it in items] == [111111]
    assert items[0].thumb == "https://ehgt.org/real.jpg"


def test_get_fixed_preview_thumb_url_sxj() -> None:
    keep = "https://ehgt.org/aa/bb/thumb-alpha.jpg"
    assert get_fixed_preview_thumb_url(keep) == keep
    assert get_fixed_preview_thumb_url(_SXJ_THUMB_EHGT) == _SXJ_THUMB_EHGT
    s_url = f"https://s.exhentai.org/t/31/7a/{_SXJ_THUMB_LAST}"
    t_url = f"https://exhentai.org/t/31/7a/{_SXJ_THUMB_LAST}"
    assert get_fixed_preview_thumb_url(s_url) == _SXJ_THUMB_EHGT
    assert get_fixed_preview_thumb_url(t_url) == _SXJ_THUMB_EHGT
    assert get_fixed_preview_thumb_url(f"//{s_url.split('://', 1)[1]}") == _SXJ_THUMB_EHGT
    short = "https://s.exhentai.org/t/foo.jpg"
    nomatch = "https://s.exhentai.org/t/xx/yy/zzzz.jpg"
    assert get_fixed_preview_thumb_url(short) == short
    assert get_fixed_preview_thumb_url(nomatch) == nomatch
    assert _usable_thumb_src(keep) == keep
    assert _usable_thumb_src(s_url) == _SXJ_THUMB_EHGT
    assert _usable_thumb_src(short) is None
    assert _usable_thumb_src(nomatch) is None
    assert _usable_thumb_src("blank.gif") is None
    assert _usable_thumb_src("https://ehgt.org/real.jpg") == "https://ehgt.org/real.jpg"
    assert _usable_thumb_src("http://ehgt.org/real.jpg") == "https://ehgt.org/real.jpg"


def test_parse_search_page_rewrites_preview_thumbs_to_ehgt() -> None:
    items, _ = parse_search_page(SEARCH_SXJ_THUMB_HTML)
    by_gid = {it.gid: it.thumb for it in items}
    assert by_gid[111111] == _SXJ_THUMB_EHGT
    assert by_gid[222222] == _SXJ_THUMB_EHGT
    assert by_gid[333333] is None


SEARCH_EH_COMPACT_W_HTML = """
<html><body>
<table class="itg gltc">
<tr><th></th><th>Published</th><th>Title</th></tr>
<tr>
  <td class="gl1c glcat"><div class="cn ct1">Misc</div></td>
  <td class="gl2c">
    <div class="glcut" id="ic4166139"></div>
    <div class="glthumb" id="it4166139" style="top:-22px;height:187px">
      <div><img style="height:141px;width:250px" alt="Compact Cover"
        src="https://ehgt.org/w/02/620/92376-8kcfz9rc.webp" /></div>
      <div><div class="ir" title="Average: 4.00"></div><div>15 pages</div></div>
    </div>
    <div class="gldown"><a href="/gallerytorrents.php?gid=4166139&amp;t=9c458b8c1d">
      <img src="https://ehgt.org/g/t.png" alt="T" title="Show torrents" /></a></div>
  </td>
  <td class="gl3c glname">
    <a href="https://e-hentai.org/g/4166139/9c458b8c1d/"><div class="glink">Compact Cover</div></a>
  </td>
</tr>
</table>
</body></html>
"""

SEARCH_EH_EXTENDED_HTML = """
<html><body>
<table class="itg glte">
<tr>
  <td class="gl1e"><div>
    <a href="https://e-hentai.org/g/222222/bbbbbb/">
      <img src="https://ehgt.org/w/01/704/00138-24abcd.webp" alt="">
    </a>
  </div></td>
  <td class="gl2e">
    <div class="gl3e"><div>12 pages</div><div class="ir" title="Average: 3.00"></div></div>
    <div class="gl4e glname">
      <a href="https://e-hentai.org/g/222222/bbbbbb/"><div class="glink">Extended Cover</div></a>
    </div>
  </td>
</tr>
</table>
</body></html>
"""

SEARCH_EH_THUMBNAIL_HTML = """
<html><body>
<div class="itg gld">
  <div class="gl1t">
    <div class="gl3t">
      <a href="https://e-hentai.org/g/333333/cccccc/">
        <img src="blank.gif" data-src="https://ehgt.org/w/02/112/77385-rdf9iok6.webp">
      </a>
    </div>
    <a href="https://e-hentai.org/g/333333/cccccc/"><div class="glink">Thumb Cover</div></a>
    <div class="gl5t"><div>8 pages</div></div>
  </div>
</div>
</body></html>
"""


def test_parse_search_page_compact_glthumb_w_webp() -> None:
    items, _ = parse_search_page(SEARCH_EH_COMPACT_W_HTML, "https://e-hentai.org")
    assert [it.gid for it in items] == [4166139]
    assert items[0].thumb == "https://ehgt.org/w/02/620/92376-8kcfz9rc.webp"
    assert items[0].pages == 15


def test_parse_search_page_extended_gl1e_and_thumbnail_gl3t() -> None:
    ext, _ = parse_search_page(SEARCH_EH_EXTENDED_HTML, "https://e-hentai.org")
    assert ext[0].gid == 222222
    assert ext[0].thumb == "https://ehgt.org/w/01/704/00138-24abcd.webp"
    th, _ = parse_search_page(SEARCH_EH_THUMBNAIL_HTML, "https://e-hentai.org")
    assert th[0].gid == 333333
    assert th[0].thumb == "https://ehgt.org/w/02/112/77385-rdf9iok6.webp"


def test_usable_thumb_src_skips_chrome_and_rewrites_w_path() -> None:
    w_url = "https://ehgt.org/w/02/620/92376-8kcfz9rc.webp"
    assert _usable_thumb_src(w_url) == w_url
    assert _usable_thumb_src("https://ehgt.org/g/t.png") is None
    assert _usable_thumb_src("https://ehgt.org/g/td.png") is None
    s_w = "https://s.exhentai.org/w/02/620/92376-8kcfz9rc.webp"
    assert get_fixed_preview_thumb_url(s_w) == w_url
    assert _usable_thumb_src(s_w) == w_url


def test_classify_search_body_sad_panda_empty_expired() -> None:
    assert classify_search_body("Sad Panda\n") == "no_exhentai_access"
    assert classify_search_body("") == "challenge"
    assert classify_search_body("   ") == "challenge"
    assert classify_search_body("expired login session") == "not_logged_in"
    assert classify_search_body(SEARCH_LIST_HTML) == "ok"


def test_parse_category_param_mask_and_names() -> None:
    assert parse_category_param(None) is None
    assert parse_category_param("") is None
    assert parse_category_param("0") == 0
    assert parse_category_param("2") == 2
    assert parse_category_param("manga") == 1023 ^ 2
    with pytest.raises(HTTPException) as exc:
        parse_category_param("nope")
    assert exc.value.status_code == 422


async def _client_for(handler) -> EhClient:
    http_client = httpx.AsyncClient(
        base_url="https://exhentai.org",
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    return EhClient(client=http_client)


@pytest.mark.asyncio
async def test_search_galleries_parses_fixture_and_sends_cursor_not_page() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.params.get("next"):
            return httpx.Response(200, text="<html><body>No hits found</body></html>")
        return httpx.Response(200, text=SEARCH_LIST_HTML)

    client = await _client_for(handler)
    try:
        first = await client.search_galleries(q="test")
        assert first.state == "ok"
        assert len(first.items) == 2
        assert first.next_cursor == "222222-1770000000"
        assert "page=" not in seen[0]
        assert "f_search=test" in seen[0]
        second = await client.search_galleries(q="test", next_cursor=first.next_cursor)
        assert "next=222222-1770000000" in seen[1]
        assert "page=" not in seen[1]
        assert second.state == "ok"
        assert second.items == []
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_search_galleries_509() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(509, text="bandwidth exceeded")

    client = await _client_for(handler)
    try:
        result = await client.search_galleries(q="test")
        assert result.state == "rate_limited"
        assert result.items == []
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_search_galleries_empty_body_is_challenge_not_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="")

    client = await _client_for(handler)
    try:
        result = await client.search_galleries(q="test")
        assert result.state == "challenge"
        assert result.state != "empty"
        assert result.items == []
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_search_galleries_sad_panda() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Sad Panda\n")

    client = await _client_for(handler)
    try:
        result = await client.search_galleries(q="test")
        assert result.state == "no_exhentai_access"
        assert result.items == []
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_search_galleries_remoteapi_302_is_challenge_not_cookie() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "remoteapi.php" in str(request.url):
            return httpx.Response(200, text="")
        return httpx.Response(
            302,
            headers={"Location": "https://forums.e-hentai.org/remoteapi.php?ex=1"},
        )

    client = await _client_for(handler)
    try:
        result = await client.search_galleries(q="test")
        assert result.state == "challenge"
        assert result.state not in {"not_logged_in", "empty", "no_exhentai_access"}
    finally:
        await client.client.aclose()


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, library_rows, fav_rows):
        self.library_rows = library_rows
        self.fav_rows = fav_rows
        self.sql: list[str] = []

    async def execute(self, statement):
        sql = str(statement).lower()
        self.sql.append(sql)
        if "favorite_items" in sql:
            return _Rows(self.fav_rows)
        return _Rows(self.library_rows)


@pytest.mark.asyncio
async def test_attach_search_badges_joins_library_and_favorites() -> None:
    items = [
        {
            "gid": 111111,
            "token": "aaaaaa",
            "title": "Alpha Gallery",
            "url": "https://exhentai.org/g/111111/aaaaaa/",
            "thumb": None,
            "category": "doujinshi",
            "pages": 24,
            "rating": 4.5,
        },
        {
            "gid": 222222,
            "token": "bbbbbb",
            "title": "Beta Gallery",
            "url": "https://exhentai.org/g/222222/bbbbbb/",
            "thumb": None,
            "category": "manga",
            "pages": 36,
            "rating": 3.25,
        },
        {
            "gid": 333333,
            "token": "cccccc",
            "title": "Gamma",
            "url": "https://exhentai.org/g/333333/cccccc/",
            "thumb": None,
            "category": None,
            "pages": None,
            "rating": None,
        },
    ]
    session = _FakeSession(library_rows=[(111111, 42)], fav_rows=[(222222, 2)])
    out = await attach_search_badges(session, items)
    assert out[0]["in_library"] is True
    assert out[0]["gallery_id"] == 42
    assert out[0]["downloaded"] is True
    assert out[0]["favorited"] is False
    assert out[1]["in_library"] is False
    assert out[1]["downloaded"] is False
    assert out[1]["favorited"] is True
    assert out[1]["favcat"] == 2
    assert out[2]["in_library"] is False
    assert out[2]["favorited"] is False
    assert any("galleries" in s for s in session.sql)
    assert any("favorite_items" in s for s in session.sql)


@pytest.mark.asyncio
async def test_eh_search_endpoint_cache_skips_repeat_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    app_state.extra.pop("eh_search_cache", None)
    calls = {"n": 0}

    class DummyClient:
        async def search_galleries(self, **kwargs):
            calls["n"] += 1
            return EhSearchResult(
                items=[
                    SearchGallery(
                        111111,
                        "aaaaaa",
                        "Alpha Gallery",
                        "https://exhentai.org/g/111111/aaaaaa/",
                        "https://ehgt.org/t.jpg",
                        "doujinshi",
                        24,
                        4.5,
                    )
                ],
                next_cursor="222222-1770000000",
                state="ok",
            )

    class DummySession:
        async def execute(self, statement):
            sql = str(statement).lower()
            if "favorite_items" in sql:
                return _Rows([(111111, 1)])
            return _Rows([(111111, 42)])

    async def dummy_get_session():
        yield DummySession()

    orig_client = app_state.eh_client
    app_state.eh_client = DummyClient()
    monkeypatch.setattr("galleryvault.app.routers.eh.get_session", dummy_get_session)
    try:
        first = await eh_search(q="test", category=None, min_rating=None, next_cursor=None)
        second = await eh_search(q="test", category=None, min_rating=None, next_cursor=None)
        assert calls["n"] == 1
        assert first["state"] == "ok"
        assert first["next"] == "222222-1770000000"
        assert first["items"][0]["in_library"] is True
        assert first["items"][0]["favorited"] is True
        assert second["items"][0]["gid"] == 111111
        await eh_search(q="test", category=None, min_rating=None, next_cursor="222222-1770000000")
        assert calls["n"] == 2
    finally:
        app_state.eh_client = orig_client
        app_state.extra.pop("eh_search_cache", None)


@pytest.mark.asyncio
async def test_search_min_rating_sends_srdd_not_page() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, text=SEARCH_LIST_HTML)

    client = await _client_for(handler)
    try:
        await client.search_galleries(q="foo", f_cats=2, min_rating=4.5)
        params = seen[0].params
        assert params.get("f_srdd") == "4"
        assert params.get("f_sr") == "on"
        assert params.get("f_cats") == "2"
        assert params.get("page") is None
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_search_list_hits_popular_watched_toplist_paths() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text=SEARCH_LIST_HTML)

    client = await _client_for(handler)
    try:
        pop = await client.search_galleries(list_type="popular")
        await client.search_galleries(list_type="watched")
        await client.search_galleries(list_type="toplist", tl=13)
        assert "/popular" in seen[0]
        assert "page=" not in seen[0]
        assert "/watched" in seen[1]
        assert "toplist.php" in seen[2]
        assert "tl=13" in seen[2]
        assert "page=" not in seen[2]
        assert [it.gid for it in pop.items] == [111111, 222222]
    finally:
        await client.client.aclose()


def test_parse_favorite_note_from_html() -> None:
    from galleryvault.services.eh_client import parse_favorite_note

    html = '<div id="favnote111111">keep this copy</div>'
    assert parse_favorite_note(html, 111111) == "keep this copy"
    assert parse_favorite_note("<div class='glnote'>hello</div>", 1) == "hello"
    assert parse_favorite_note("<html></html>", 1) is None
