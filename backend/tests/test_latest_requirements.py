
import httpx
import pytest

from galleryvault.config import EDITABLE_SETTINGS, Settings
from galleryvault.services.eh_client import (
    EhClient,
    EhClientError,
    GalleryGoneError,
    _parse_category,
    _parse_favorite_categories,
)


def test_settings_persistence_excludes_auth_secrets() -> None:
    # The DB-persisted payload must never carry auth secrets.
    settings = Settings()
    payload = {key: getattr(settings, key) for key in EDITABLE_SETTINGS}
    assert "auth_secret" not in payload
    assert "auth_password_hash" not in payload
    # Secrets live in the separate runtime_auth DB row instead.
    assert "auth_secret" in settings.model_fields_set or settings.auth_secret
    # User-editable settings are the only thing persisted to user_settings.
    assert "library_roots" in EDITABLE_SETTINGS
    assert "auth_required" in EDITABLE_SETTINGS


def test_favorite_category_markup_supports_options_and_anchors() -> None:
    body = '<select><option value="0">Inbox &amp; New</option></select><a href="?favcat=3">Art</a>'
    assert _parse_favorite_categories(body) == {0: "Inbox & New", 3: "Art"}


def test_favorite_category_markup_supports_exhentai_favorite_panels() -> None:
    body = '<div class="fp" onclick="document.location=\'/favorites.php?favcat=0\'"><div>12</div><div>New items</div></div>'
    assert _parse_favorite_categories(body) == {0: "New items"}


@pytest.mark.asyncio
async def test_favorite_category_fetch_only_requests_favorites_page() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(200, text='<option value="1">Reading</option>')

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(client=http_client)
        assert await client.fetch_favorite_categories() == {1: "Reading"}
    assert requests == ["/favorites.php"]


@pytest.mark.asyncio
async def test_fetch_favorites_follows_paging() -> None:
    requests: list[str] = []

    def page_body(cursor: str | None, base: int) -> str:
        galleries = "".join(
            f'<a href="/g/{1000 + base + i}/{f"{base + i:02d}abcdef"}/">Gallery {i}</a>'
            for i in range(50)
        )
        if cursor:
            galleries += f'<script>var nexturl="https://exhentai.test/favorites.php?favcat=0&next={cursor}";</script>'
        return galleries

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = request.url.params
        requests.append(path + "?" + str(params))
        if params.get("next"):
            return httpx.Response(200, text=page_body(None, 50))
        return httpx.Response(200, text=page_body("462571-1777996391", 0))

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(client=http_client)
        items = await client.fetch_favorites(0)
    assert len(items) == 100  # page 1 (50) + page 2 (50), cursor walk stops
    assert [r.split("?")[0] for r in requests] == ["/favorites.php", "/favorites.php"]
    assert "next=462571-1777996391" in requests[1]


def test_parse_category_supports_exhentai_cs_ct2_markup() -> None:
    body = (
        '<div class="cs ct2" onclick="document.location='
        "'https://exhentai.org/doujinshi'\">Doujinshi</div>"
    )
    assert _parse_category(body) == "doujinshi"
    assert _parse_category("<span>Nothing</span>") == "misc"


def test_category_normalization_includes_image_set_and_asianporn() -> None:
    from galleryvault.scanners.base import CATEGORIES, normalize_category

    assert "image_set" in CATEGORIES and "asianporn" in CATEGORIES
    assert normalize_category("Image Set") == "image_set"
    assert normalize_category("Asian Porn") == "asianporn"
    assert normalize_category("Imageset") == "misc"


@pytest.mark.asyncio
async def test_exhentai_404_raises_gallery_gone() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(client=http_client)
        with pytest.raises(GalleryGoneError):
            await client.fetch_gallery_metadata(12345, "sometoken")


@pytest.mark.asyncio
async def test_exhentai_page_404_raises_eh_client_error_not_gallery_gone() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/s/")
        return httpx.Response(404)

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(client=http_client)
        with pytest.raises(EhClientError) as exc_info:
            await client._get("/s/abc12345/12345-1")
        assert not isinstance(exc_info.value, GalleryGoneError)


@pytest.mark.asyncio
async def test_fetch_gallery_filters_out_comment_and_external_links() -> None:
    html_content = """
    <html>
    <head><title>Test Gallery - ExHentai.org</title></head>
    <body>
    <h1 id="gn">Test Gallery</h1>
    <h1 id="gj">テストギャラリー</h1>
    <div id="gdt">
        <a href="https://exhentai.test/s/aaaa1111/12345-1">Page 1</a>
        <a href="https://exhentai.test/s/bbbb2222/12345-2">Page 2</a>
    </div>
    <div id="cdiv">
        <p>Check out another gallery at <a href="https://exhentai.test/s/cccc3333/99999-1">Other Gallery Page</a></p>
        <p>Or invalid link <a href="https://exhentai.test/s/dddd4444/invalid">Invalid</a></p>
    </div>
    </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api.php":
            return httpx.Response(200, json={"gmetadata": [{"gid": 12345, "filecount": "2"}]})
        if request.url.path.startswith("/g/12345/token123"):
            return httpx.Response(200, text=html_content)
        return httpx.Response(404)

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(client=http_client)
        gallery = await client.fetch_gallery(12345, "token123", resolve_urls=False)
        assert len(gallery.pages) == 2
        assert gallery.pages[0].url == "https://exhentai.test/s/aaaa1111/12345-1"
        assert gallery.pages[1].url == "https://exhentai.test/s/bbbb2222/12345-2"


@pytest.mark.asyncio
async def test_check_login_classifies_response_and_retries() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        assert request.url.path == "/uconfig.php"
        requests += 1
        if requests == 1:
            # Transient transport failure: must be retried, not reported as a
            # login failure (ExHentai's occasional anti-bot challenge).
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, text="<html>User Control Panel</html>")

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(
            client=http_client,
            settings=Settings(
                exhentai_cookies={"ipb_member_id": "12345"}
            ),
        )
        state, _ = await client.check_login()
        assert state == "ok"
        assert requests == 2  # first attempt failed, retry succeeded


@pytest.mark.asyncio
async def test_check_login_reports_not_logged_in() -> None:
    """A dead session answers the member page with exactly ``expired login session``."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/uconfig.php"
        return httpx.Response(200, text="expired login session")

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(
            client=http_client,
            settings=Settings(
                exhentai_cookies={"ipb_member_id": "12345"},
            ),
        )
        assert (await client.check_login())[0] == "not_logged_in"


@pytest.mark.asyncio
async def test_check_login_empty_body_reports_failed() -> None:
    """An empty HTTP 200 (anti-bot challenge) is a retryable failure, not a
    dead session: it must surface as ``failed``, never ``not_logged_in``."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/uconfig.php"
        return httpx.Response(200, text="")

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(
            client=http_client,
            settings=Settings(
                exhentai_cookies={
                    "ipb_member_id": "12345",
                    "ipb_pass_hash": "0123456789abcdef",
                },
            ),
        )
        state, _ = await client.check_login()
        assert state == "failed"


@pytest.mark.asyncio
async def test_check_login_reports_no_exhentai_access() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Sad Panda\n")

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(
            client=http_client,
            settings=Settings(
                exhentai_cookies={"ipb_member_id": "12345"},
            ),
        )
        assert (await client.check_login())[0] == "no_exhentai_access"


@pytest.mark.asyncio
async def test_check_login_fails_after_two_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(client=http_client, settings=Settings())
        state, detail = await client.check_login()
        assert state == "failed"
        assert "ConnectError" in detail


def test_gallery_dirname_matches_ehviewer_style() -> None:
    from galleryvault.services.downloader import gallery_dirname

    assert gallery_dirname(560135, "(COMIC1☆5) [TIES (タケイオーキ)] ...", "Title") == (
        "560135-(COMIC1☆5) [TIES (タケイオーキ)]"
    )
    # Without a Japanese title it falls back to the display title.
    assert gallery_dirname(560135, None, "Some English Title") == "560135-Some English Title"


def test_gallery_dirname_download_title_modes() -> None:
    from galleryvault.services.downloader import gallery_dirname

    title_jpn = "(COMIC1☆5) [TIES (タケイオーキ)] 標題"
    title = "Some English Title"
    # Default and explicit japanese prefer the Japanese title.
    assert gallery_dirname(1, title_jpn, title) == f"1-{title_jpn}"
    assert gallery_dirname(1, title_jpn, title, mode="japanese") == f"1-{title_jpn}"
    # english prefers the romaji/English title.
    assert gallery_dirname(1, title_jpn, title, mode="english") == "1-Some English Title"
    # No title at all falls back to the bare gid.
    assert gallery_dirname(1, None, None, mode="english") == "1"


def test_gallery_dirname_truncates_utf8_bytes() -> None:
    from galleryvault.services.downloader import _truncate_utf8, gallery_dirname

    # 90 CJK chars = 270 UTF-8 bytes (> 255); must be cut at a char boundary.
    long_title = "啊" * 90
    name = gallery_dirname(7, long_title, None)
    assert name.startswith("7-")
    assert len(name.encode("utf-8")) <= 255
    # The suffix stays decodable (no trailing partial multibyte char).
    _truncate_utf8("啊" * 100, 10).encode("utf-8").decode("utf-8")


def test_parse_login_state() -> None:
    from galleryvault.services.eh_client import parse_login_state

    # A member page with real content means a valid session.
    assert parse_login_state("<html>User Control Panel</html>", "12345") == "ok"
    assert parse_login_state("user id 12345 logged in", "12345") == "ok"
    # ExHentai's own expired-session marker answers HTTP 200 with this body.
    assert parse_login_state("expired login session", "12345") == "not_logged_in"
    # An empty body is an anti-bot challenge / transient glitch: retry, don't
    # report a dead session (which would prompt a pointless cookie reset).
    assert parse_login_state("", "12345") == "failed"
    # has_cookies no longer overrides the body classification.
    assert parse_login_state("", "12345", has_cookies=True) == "failed"
    # Sad-Panda / banned pages carry no content.
    assert parse_login_state("Sad Panda\n", "12345") == "no_exhentai_access"


def test_tag_translation_namespace_and_name() -> None:
    from galleryvault.services.tag_translation import (
        NAMESPACE_LABELS_ZH,
        translated_tag,
    )

    assert NAMESPACE_LABELS_ZH["artist"] == "作者"
    # Ehviewer-style namespace labels take precedence over ehsyringe frontmatter.
    assert NAMESPACE_LABELS_ZH["group"] == "社团"
    assert NAMESPACE_LABELS_ZH["cosplay"] == "角色扮演"
    # Built-in namespaces still resolve; unknown tags pass through unchanged.
    assert translated_tag("artist", "tanaka") == ("作者", "tanaka")
    assert translated_tag("unknown_ns", "foo")[1] == "foo"
    # The bundled ehsyringe database provides real translations.
    zh = translated_tag("language", "chinese")
    assert zh[0] == "语言"
    assert zh[1] and zh[1] != "chinese"


def test_tag_translation_strips_markdown_icons() -> None:
    from galleryvault.services.tag_translation import (
        clean_display,
        load_translations,
        translate_tag,
    )

    assert (
        clean_display(
            "![贝合图标](https://raw.githubusercontent.com/wiki/x/tribadism.webp)贝合"
        )
        == "贝合"
    )
    assert clean_display("![](https://i.pixiv.cat/a.jpg)NT00") == "NT00"
    assert clean_display('![图标](# "https://x/y.webp")扶她') == "扶她"
    assert clean_display("  A  B  ") == "A B"
    assert len(clean_display("x" * 500)) <= 60
    # Translated values are cleaned transparently; untranslated names pass through.
    load_translations("galleryvault/data/tag_translations.json")
    assert "](" not in (translate_tag("female", "tribadism") or "")


def test_search_zh_reverse_matches_chinese_query() -> None:
    from galleryvault.services.tag_translation import load_translations, search_zh

    load_translations("galleryvault/data/tag_translations.json", reset=True)
    hits = search_zh("巨乳", limit=20)
    assert any(ns == "female" and name == "big breasts" for ns, name, _ in hits)
    assert search_zh("", limit=5) == []
    # English-only queries are not handled by the Chinese reverse search.
    assert all("\u4e00" <= display[:1] <= "\u9fff" for _, _, display in hits)


def test_search_zh_exact_maps_only_one_to_one_translations() -> None:
    from galleryvault.services.tag_translation import load_translations, search_zh_exact

    load_translations("galleryvault/data/tag_translations.json", reset=True)
    # "动图" maps one-to-one onto the animated tag (misc/other alias both store it).
    hit = search_zh_exact("动图")
    assert hit is not None and hit[1] == "animated"
    # "巨乳" maps exactly onto female:big breasts.
    assert search_zh_exact("巨乳")[0:2] == ("female", "big breasts")
    # "中国" is NOT a translation of any tag (language:chinese translates to 汉语),
    # so it must not be promoted to a tag filter.
    assert search_zh_exact("中国") is None
    assert search_zh_exact("") is None


def test_is_public_site() -> None:
    from galleryvault.services.settings_service import is_public_site

    assert is_public_site("https://e-hentai.org")
    assert is_public_site("https://my.e-hentai.org")
    assert not is_public_site("https://exhentai.org")
    assert not is_public_site("https://www.exhentai.org")
    assert not is_public_site("")
    assert not is_public_site("not a url")


def test_parse_gallery_titles_reads_gn_and_gj() -> None:
    from galleryvault.services.eh_client import _parse_gallery_titles

    body = (
        '<h1 id="gn">Display Title</h1>'
        '<h1 id="gj">日本語タイトル</h1>'
        '<div class="gt">artist: alice</div>'
    )
    title, title_jpn = _parse_gallery_titles(body)
    assert title == "Display Title"
    assert title_jpn == "日本語タイトル"


@pytest.mark.asyncio
async def test_fetch_gallery_by_category_requests_listing() -> None:

    from galleryvault.services.eh_client import EhClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("f_cats") == "2"
        return httpx.Response(200, text='<a href="/g/4139697/bb74ca821e/">x</a>')

    async with httpx.AsyncClient(
        base_url="https://exhentai.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        client = EhClient(client=http_client)
        result = await client.fetch_gallery_by_category("manga")
    assert result == (4139697, "bb74ca821e")
    assert await client.fetch_gallery_by_category("bogus") is None



def test_parse_favorite_counts_from_fp_blocks() -> None:
    from galleryvault.services.eh_client import _parse_favorite_counts

    body = (
        '<div class="fp" onclick="document.location=\'/favorites.php?favcat=0\'">'
        '<div>2233</div><div>0 看过的番</div></div>'
        '<div class="fp" onclick="document.location=\'/favorites.php?favcat=1\'">'
        '<div>234</div><div>1 长篇大作</div></div>'
    )
    assert _parse_favorite_counts(body) == {0: 2233, 1: 234}


def test_parse_file_size_units() -> None:
    from galleryvault.services.eh_client import _parse_file_size

    assert _parse_file_size(
        '<td class="gdt1">File Size:</td><td class="gdt2">32.63 MiB</td>'
    ) == int(32.63 * 1024 * 1024)
    assert _parse_file_size(
        '<td class="gdt1">File Size:</td><td class="gdt2">1.2 GB</td>'
    ) == int(1.2 * 1024**3)
    assert _parse_file_size("<p>no size here</p>") is None
