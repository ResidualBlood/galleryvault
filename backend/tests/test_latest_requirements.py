
import httpx
import pytest

from galleryvault.config import EDITABLE_SETTINGS, Settings
from galleryvault.services.eh_client import (
    EhClient,
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


def test_gallery_dirname_matches_ehviewer_style() -> None:
    from galleryvault.services.downloader import gallery_dirname

    assert gallery_dirname(560135, "(COMIC1☆5) [TIES (タケイオーキ)] ...", "Title") == (
        "560135-(COMIC1☆5) [TIES (タケイオーキ)]"
    )
    # Without a Japanese title it falls back to the display title.
    assert gallery_dirname(560135, None, "Some English Title") == "560135-Some English Title"


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
    from galleryvault.app.main import _is_public_site

    assert _is_public_site("https://e-hentai.org")
    assert _is_public_site("https://my.e-hentai.org")
    assert not _is_public_site("https://exhentai.org")
    assert not _is_public_site("https://www.exhentai.org")
    assert not _is_public_site("")
    assert not _is_public_site("not a url")


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
