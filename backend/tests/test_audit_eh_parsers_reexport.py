"""Audit T17: pure parsers live in ``eh_parsers`` and ``eh_client`` re-exports them.

The transport module must keep every symbol it exported before the split (the
rest of the code and 17 test modules import from ``galleryvault.services.eh_client``)
while the parser module must stay importable without ``httpx`` or ``EhClient``.
"""

from __future__ import annotations

import subprocess
import sys

from galleryvault.services import eh_client, eh_parsers

# Every module-level symbol ``eh_client`` exposed before the split.
_EXPECTED_EXPORTS = (
    "ALLOWED_EH_DOMAINS",
    "ARCHIVER_DOWNLOAD_LINK_RE",
    "ARCHIVER_LOCATION_RE",
    "ARCHIVE_COST_RE",
    "ARCHIVE_FUNDS_RE",
    "ARCHIVE_GP_BALANCE_RE",
    "ARCHIVE_SIZE_RE",
    "ArchiveExpiredError",
    "ArchiveInfo",
    "EHVIEWER_ACCEPT",
    "EHVIEWER_ACCEPT_LANGUAGE",
    "EHVIEWER_USER_AGENT",
    "EXHENTAI_API_CHUNK_SIZE",
    "EhChallengeError",
    "EhClient",
    "EhClientError",
    "EhImageSlowError",
    "EhParseError",
    "EhQuotaExceededError",
    "EhSearchResult",
    "FavoriteData",
    "FavoriteItems",
    "GALLERY_RE",
    "GalleryData",
    "GalleryGoneError",
    "GalleryPageData",
    "GalleryReplacedError",
    "IMAGE_LIMIT_PLAIN_RE",
    "IMAGE_LIMIT_RE",
    "IMAGE_LIMIT_SIMPLE_RE",
    "IMAGE_RE",
    "PAGE_RE",
    "SHOWKEY_RE",
    "SHOWPAGE_IMAGE_RE",
    "SHOWPAGE_ORIGIN_PROMPT_RE",
    "SHOWPAGE_ORIGIN_RE",
    "SHOWPAGE_SKIP_KEY_RE",
    "SearchGallery",
    "ShowkeyState",
    "TAG_ANCHOR_RE",
    "VIEWER_HREF_RE",
    "_FAVORITES_AUTH_FAILURE_MARKERS",
    "_FAVORITES_PAGE_FAVCAT_RE",
    "_NEWER_HINT",
    "_NEXT_CURSOR_RE",
    "_SHARED_LIMITERS",
    "_TOPLIST_CURSOR_RE",
    "_UCONFIG_LOGIN_FAILURE_MARKERS",
    "_UCONFIG_POSITIVE_MARKERS",
    "_content_range_total",
    "_cursor_from_url",
    "_favorites_next_url",
    "_favorites_page_favcats",
    "_is_allowed_eh_host",
    "_is_auth_failure_page",
    "_is_exhentai_org_host",
    "_is_favorites_auth_failure_page",
    "_is_ip_banned_page",
    "_is_uconfig_page",
    "_page_token_from_href",
    "_parse_archive_cost",
    "_parse_archive_info",
    "_parse_archive_size",
    "_parse_archiver_download_url",
    "_parse_category",
    "_parse_favorite_categories",
    "_parse_favorite_counts",
    "_parse_file_size",
    "_parse_gallery_titles",
    "_parse_tags",
    "_quota_exceeded_error",
    "_report_cookie_health",
    "_retry_after_seconds",
    "_search_category",
    "_search_item_window",
    "_search_next_cursor",
    "_search_pages",
    "_search_rating",
    "_search_response_urls",
    "_search_thumb",
    "_shared_limiter",
    "_text",
    "_thumb_from_img_attrs",
    "_thumbs_from_listing_cells",
    "_toplist_next_cursor",
    "_usable_thumb_src",
    "_validate_favorites_write_response",
    "classify_search_body",
    "classify_search_response",
    "cookie_health_loop",
    "get_fixed_preview_thumb_url",
    "logger",
    "parse_favorite_note",
    "parse_gallery_url",
    "parse_login_state",
    "parse_newer_gallery",
    "parse_search_page",
    "probe_cookie_health",
)


def test_eh_client_reexports_every_original_symbol() -> None:
    missing = [name for name in _EXPECTED_EXPORTS if not hasattr(eh_client, name)]
    assert missing == []


def test_eh_client_all_lists_public_parsers() -> None:
    for name in eh_parsers.__all__:
        assert name in eh_client.__all__
        assert getattr(eh_client, name) is getattr(eh_parsers, name)


def test_parsers_module_does_not_expose_client_or_httpx() -> None:
    assert not hasattr(eh_parsers, "EhClient")
    assert not hasattr(eh_parsers, "httpx")
    imported = {
        getattr(value, "__name__", "")
        for value in vars(eh_parsers).values()
    }
    assert "httpx" not in imported
    assert "EhClient" not in imported


def test_parsers_module_imports_without_httpx() -> None:
    code = (
        "import sys; import galleryvault.services.eh_parsers; "
        "assert 'httpx' not in sys.modules, 'eh_parsers pulled in httpx'; "
        "assert 'galleryvault.services.eh_client' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_reexported_parsers_keep_their_behaviour() -> None:
    assert eh_client.parse_gallery_url("/g/123/abc123/") == (123, "abc123")
    assert eh_client.parse_gallery_url("https://exhentai.org/g/9/ff/") == (9, "ff")
    assert eh_client.parse_login_state("expired login session") == "not_logged_in"
    assert eh_client.classify_search_body("Sad Panda") == "no_exhentai_access"
    assert issubclass(eh_client.EhQuotaExceededError, eh_client.EhClientError)
    assert eh_client.GalleryData is eh_parsers.GalleryData
