"""Pure ExHentai parsers, split by domain.

Every module here is transport-free (no ``httpx``, no client, no app/db
imports).  ``galleryvault.services.eh_parsers`` re-exports all of them under
the historical import path; its ``__all__`` stays the public surface.
"""

from __future__ import annotations

from .archive import *
from .errors import *
from .favorites import *
from .gallery import *
from .search import *
from .showpage import *

__all__ = [
    "ARCHIVER_DOWNLOAD_LINK_RE",
    "ARCHIVER_LOCATION_RE",
    "ARCHIVE_COST_RE",
    "ARCHIVE_FUNDS_RE",
    "ARCHIVE_GP_BALANCE_RE",
    "ARCHIVE_SIZE_RE",
    "GALLERY_RE",
    "IMAGE_LIMIT_PLAIN_RE",
    "IMAGE_LIMIT_RE",
    "IMAGE_LIMIT_SIMPLE_RE",
    "IMAGE_RE",
    "JUMP_VALUES",
    "PAGE_RE",
    "SHOWKEY_RE",
    "SHOWPAGE_IMAGE_RE",
    "SHOWPAGE_ORIGIN_PROMPT_RE",
    "SHOWPAGE_ORIGIN_RE",
    "SHOWPAGE_SKIP_KEY_RE",
    "TAG_ANCHOR_RE",
    "VIEWER_HREF_RE",
    "ArchiveExpiredError",
    "ArchiveInfo",
    "EhAuthRequiredError",
    "EhBannedError",
    "EhChallengeError",
    "EhClientError",
    "EhImageSlowError",
    "EhParseError",
    "EhQuotaExceededError",
    "EhSearchResult",
    "FavoriteData",
    "FavoriteItems",
    "GalleryData",
    "GalleryGoneError",
    "GalleryPageData",
    "GalleryReplacedError",
    "OnlineGalleryDetail",
    "PageThumb",
    "PreviewItem",
    "PreviewPage",
    "SearchGallery",
    "ShowkeyState",
    "classify_search_body",
    "get_fixed_preview_thumb_url",
    "normalize_jump",
    "normalize_seek",
    "parse_favorite_note",
    "parse_gallery_preview",
    "parse_gallery_url",
    "parse_login_state",
    "parse_newer_gallery",
    "parse_online_gallery",
    "parse_search_page",
    "parse_search_prev_cursor",
]
