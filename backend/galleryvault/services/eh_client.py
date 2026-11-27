"""Composition facade for the ExHentai client.

The transport, loop-wide limiters and in-flight counter live in
:mod:`galleryvault.services.eh.session`; per-domain behaviour lives in
:mod:`galleryvault.services.eh.{gallery,search,favorites,archive,images}`.
``EhClient`` keeps the historical public surface and delegates one-to-one, so
instance-level stubs (``client._get = fake``) and the parser re-exports keep
working unchanged.
"""

from __future__ import annotations

import logging
from typing import Any, Self

from ..config import Settings
from .eh import archive as _archive
from .eh import favorites as _favorites
from .eh import gallery as _gallery
from .eh import images as _images
from .eh import search as _search
from .eh import session as _session
from .eh.favorites import (  # noqa: F401
    _validate_favorites_write_response,
)
from .eh.gallery import _page_token_from_href  # noqa: F401
from .eh.search import (  # noqa: F401
    _search_response_urls,
    classify_search_response,
)
from .eh.session import (  # noqa: F401
    _SHARED_LIMITERS,
    ALLOWED_EH_DOMAINS,
    EHVIEWER_ACCEPT,
    EHVIEWER_ACCEPT_LANGUAGE,
    EHVIEWER_USER_AGENT,
    EXHENTAI_API_CHUNK_SIZE,
    _is_allowed_eh_host,
    _quota_exceeded_error,
    _retry_after_seconds,
    _shared_limiter,
)
from .eh_parsers import (  # noqa: F401 - re-exported for backwards compatibility
    _FAVORITES_AUTH_FAILURE_MARKERS,
    _FAVORITES_PAGE_FAVCAT_RE,
    _NEWER_HINT,
    _NEXT_CURSOR_RE,
    _TOPLIST_CURSOR_RE,
    _UCONFIG_LOGIN_FAILURE_MARKERS,
    _UCONFIG_POSITIVE_MARKERS,
    ARCHIVE_COST_RE,
    ARCHIVE_FUNDS_RE,
    ARCHIVE_GP_BALANCE_RE,
    ARCHIVE_SIZE_RE,
    ARCHIVER_DOWNLOAD_LINK_RE,
    ARCHIVER_LOCATION_RE,
    GALLERY_RE,
    IMAGE_LIMIT_PLAIN_RE,
    IMAGE_LIMIT_RE,
    IMAGE_LIMIT_SIMPLE_RE,
    IMAGE_RE,
    JUMP_VALUES,
    PAGE_RE,
    SHOWKEY_RE,
    SHOWPAGE_IMAGE_RE,
    SHOWPAGE_ORIGIN_PROMPT_RE,
    SHOWPAGE_ORIGIN_RE,
    SHOWPAGE_SKIP_KEY_RE,
    TAG_ANCHOR_RE,
    VIEWER_HREF_RE,
    ArchiveExpiredError,
    ArchiveInfo,
    EhAuthRequiredError,
    EhBannedError,
    EhChallengeError,
    EhClientError,
    EhImageSlowError,
    EhParseError,
    EhQuotaExceededError,
    EhSearchResult,
    FavoriteData,
    FavoriteItems,
    GalleryData,
    GalleryGoneError,
    GalleryPageData,
    GalleryReplacedError,
    OnlineGalleryDetail,
    PageThumb,
    PreviewItem,
    PreviewPage,
    SearchGallery,
    ShowkeyState,
    _content_range_total,
    _cursor_from_url,
    _favorites_next_url,
    _favorites_page_favcats,
    _is_auth_failure_page,
    _is_exhentai_org_host,
    _is_favorites_auth_failure_page,
    _is_ip_banned_page,
    _is_uconfig_page,
    _parse_archive_cost,
    _parse_archive_info,
    _parse_archive_size,
    _parse_archiver_download_url,
    _parse_category,
    _parse_favorite_categories,
    _parse_favorite_counts,
    _parse_file_size,
    _parse_gallery_titles,
    _parse_tags,
    _search_category,
    _search_item_window,
    _search_next_cursor,
    _search_pages,
    _search_rating,
    _search_thumb,
    _text,
    _thumb_from_img_attrs,
    _thumbs_from_listing_cells,
    _toplist_next_cursor,
    _usable_thumb_src,
    classify_search_body,
    get_fixed_preview_thumb_url,
    normalize_jump,
    normalize_seek,
    parse_favorite_note,
    parse_gallery_preview,
    parse_gallery_url,
    parse_login_state,
    parse_newer_gallery,
    parse_online_gallery,
    parse_search_page,
    parse_search_prev_cursor,
)

__all__ = [
    "ALLOWED_EH_DOMAINS",
    "ARCHIVER_DOWNLOAD_LINK_RE",
    "ARCHIVER_LOCATION_RE",
    "ARCHIVE_COST_RE",
    "ARCHIVE_FUNDS_RE",
    "ARCHIVE_GP_BALANCE_RE",
    "ARCHIVE_SIZE_RE",
    "EHVIEWER_ACCEPT",
    "EHVIEWER_ACCEPT_LANGUAGE",
    "EHVIEWER_USER_AGENT",
    "EXHENTAI_API_CHUNK_SIZE",
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
    "EhClient",
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
    "classify_search_response",
    "cookie_health_loop",
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
    "probe_cookie_health",
]

logger = logging.getLogger(__name__)


class EhClient:
    """Facade over :class:`~galleryvault.services.eh.session.EhSession`."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: Any = None,
        transport: Any = None,
        max_concurrency: int = 6,
    ) -> None:
        self._session = _session.EhSession(
            self,
            settings=settings,
            client=client,
            transport=transport,
            max_concurrency=max_concurrency,
        )

    @property
    def settings(self) -> Settings:
        return self._session.settings

    @settings.setter
    def settings(self, value: Settings) -> None:
        self._session.settings = value

    @property
    def client(self) -> Any:
        return self._session.client

    @client.setter
    def client(self, value: Any) -> None:
        self._session.client = value

    @property
    def _semaphore(self) -> Any:
        return self._session._semaphore

    @_semaphore.setter
    def _semaphore(self, value: Any) -> None:
        self._session._semaphore = value

    @property
    def _image_semaphore(self) -> Any:
        return self._session._image_semaphore

    @_image_semaphore.setter
    def _image_semaphore(self, value: Any) -> None:
        self._session._image_semaphore = value

    @property
    def _archive_semaphore(self) -> Any:
        return self._session._archive_semaphore

    @_archive_semaphore.setter
    def _archive_semaphore(self, value: Any) -> None:
        self._session._archive_semaphore = value

    @property
    def _stream_count(self) -> int:
        return self._session._stream_count

    @_stream_count.setter
    def _stream_count(self, value: int) -> None:
        self._session._stream_count = value

    @property
    def in_flight_requests(self) -> int:
        """Number of long-lived transfers (image / cover / archive) still running."""
        return self._session.in_flight_requests

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._session.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        return await self._session._request(method, url, **kwargs)

    @staticmethod
    def _status_error(response: Any) -> Any:
        return _session.EhSession._status_error(response)

    def _raise_for_status(self, response: Any, *, gallery_404: bool = False) -> None:
        self._session._raise_for_status(response, gallery_404=gallery_404)

    async def _get(self, url: str, **kwargs: Any) -> Any:
        return await self._session._get(url, **kwargs)

    async def check_login(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery.check_login(self, *args, **kwargs)

    async def probe_challenge(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery.probe_challenge(self, *args, **kwargs)

    async def fetch_gallery_metadata(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery.fetch_gallery_metadata(self, *args, **kwargs)

    async def _fetch_gallery_html(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery._fetch_gallery_html(self, *args, **kwargs)

    async def fetch_online_gallery(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery.fetch_online_gallery(self, *args, **kwargs)

    async def fetch_gallery_preview_page(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery.fetch_gallery_preview_page(self, *args, **kwargs)

    async def fetch_gallery(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery.fetch_gallery(self, *args, **kwargs)

    async def _resolve_gallery_pages(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery._resolve_gallery_pages(self, *args, **kwargs)

    async def resolve_page(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery.resolve_page(self, *args, **kwargs)

    async def _resolve_page_from_html(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery._resolve_page_from_html(self, *args, **kwargs)

    async def _showpage(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery._showpage(self, *args, **kwargs)

    async def fetch_gmetadata(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery.fetch_gmetadata(self, *args, **kwargs)

    async def fetch_gallery_by_category(self, *args: Any, **kwargs: Any) -> Any:
        return await _gallery.fetch_gallery_by_category(self, *args, **kwargs)

    async def search_galleries(self, *args: Any, **kwargs: Any) -> Any:
        return await _search.search_galleries(self, *args, **kwargs)

    async def fetch_favorites(self, *args: Any, **kwargs: Any) -> Any:
        return await _favorites.fetch_favorites(self, *args, **kwargs)

    async def fetch_favorite_categories(self, *args: Any, **kwargs: Any) -> Any:
        return await _favorites.fetch_favorite_categories(self, *args, **kwargs)

    async def fetch_favorite_counts(self, *args: Any, **kwargs: Any) -> Any:
        return await _favorites.fetch_favorite_counts(self, *args, **kwargs)

    async def remove_favorites(self, *args: Any, **kwargs: Any) -> Any:
        return await _favorites.remove_favorites(self, *args, **kwargs)

    async def move_favorites(self, *args: Any, **kwargs: Any) -> Any:
        return await _favorites.move_favorites(self, *args, **kwargs)

    async def add_favorite(self, *args: Any, **kwargs: Any) -> Any:
        return await _favorites.add_favorite(self, *args, **kwargs)

    async def add_favorites(self, *args: Any, **kwargs: Any) -> Any:
        return await _favorites.add_favorites(self, *args, **kwargs)

    async def fetch_archive_info(self, *args: Any, **kwargs: Any) -> Any:
        return await _archive.fetch_archive_info(self, *args, **kwargs)

    async def fetch_gp_balance(self, *args: Any, **kwargs: Any) -> Any:
        return await _archive.fetch_gp_balance(self, *args, **kwargs)

    async def fetch_image_limits(self, *args: Any, **kwargs: Any) -> Any:
        return await _archive.fetch_image_limits(self, *args, **kwargs)

    async def request_archive(self, *args: Any, **kwargs: Any) -> Any:
        return await _archive.request_archive(self, *args, **kwargs)

    async def download_archive(self, *args: Any, **kwargs: Any) -> Any:
        return await _archive.download_archive(self, *args, **kwargs)

    async def _stream_archive(self, *args: Any, **kwargs: Any) -> Any:
        return await _archive._stream_archive(self, *args, **kwargs)

    async def download_image(self, *args: Any, **kwargs: Any) -> Any:
        return await _images.download_image(self, *args, **kwargs)

    async def fetch_gallery_cover(self, *args: Any, **kwargs: Any) -> Any:
        return await _images.fetch_gallery_cover(self, *args, **kwargs)

    async def download_image_with_metadata(self, *args: Any, **kwargs: Any) -> Any:
        return await _images.download_image_with_metadata(self, *args, **kwargs)

    def _parse_image_limits(self, *args: Any, **kwargs: Any) -> Any:
        return _archive._parse_image_limits(self, *args, **kwargs)


async def probe_cookie_health() -> dict[str, Any]:
    from datetime import UTC, datetime

    from ..app.dependencies import get_current_settings
    from ..app.state import app_state
    from .notifications import notify_cookie_health

    settings = get_current_settings()
    if not settings.exhentai_cookies:
        health = {
            "state": "not_configured",
            "detail": "Cookies not configured",
            "checked_at": datetime.now(UTC).isoformat(),
        }
        app_state.extra["cookie_health"] = health
        notify_cookie_health(health.get("state"), health.get("detail"))
        return health
    client = app_state.eh_client
    if client is None:
        health = {
            "state": "not_configured",
            "detail": "Client unavailable",
            "checked_at": datetime.now(UTC).isoformat(),
        }
        app_state.extra["cookie_health"] = health
        notify_cookie_health(health.get("state"), health.get("detail"))
        return health
    try:
        state, detail = await client.check_login()
        health = {
            "state": state,
            "detail": detail,
            "checked_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        health = {
            "state": "failed",
            "detail": type(exc).__name__,
            "checked_at": datetime.now(UTC).isoformat(),
        }
    app_state.extra["cookie_health"] = health
    notify_cookie_health(health.get("state"), health.get("detail"))
    return health


def _report_cookie_health(tracker: Any, health: dict[str, Any]) -> None:
    """Record a cookie-health probe result on a task tracker.

    ``check_login`` reports ``ok`` / ``not_logged_in`` / ``no_exhentai_access`` /
    ``ip_banned`` / ``failed`` (never ``valid``/``expired``), so the tracker must
    key off those names or it always reported "nothing done" and dropped the
    failure detail.
    """
    state = health.get("state")
    tracker.update(done=1 if state == "ok" else 0, total=1, stage=state)
    if state != "ok":
        tracker.update(last_error=health.get("detail") or state)


async def cookie_health_loop(interval_seconds: int = 1800) -> None:
    """Periodically probe ExHentai cookie health while the app is running.

    Interval defaults to 30 min; loop is cancellable via task cancel.
    """
    import asyncio

    # Initial delay so startup probe has a chance to run first
    try:
        await asyncio.sleep(60)
    except asyncio.CancelledError:
        return
    while True:
        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            return
        try:
            from ..app.dependencies import get_task_manager

            tm = get_task_manager()
            async with tm.track_task("cookie-health") as tracker:
                health = await probe_cookie_health()
                _report_cookie_health(tracker, health)
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001, S110
            pass
