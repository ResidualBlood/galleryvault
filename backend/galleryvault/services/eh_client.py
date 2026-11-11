"""Small, testable ExHentai HTTP and HTML client.

The parsing logic (exceptions, data classes, HTML parsers) lives in
:mod:`galleryvault.services.eh_parsers`; this module keeps the HTTP transport
and re-exports the parser symbols for backwards compatibility.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
import weakref
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, Self
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from ..config import Settings, get_settings
from ..logging import log_extra
from ..observability import observe_histogram
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
    parse_favorite_note,
    parse_gallery_url,
    parse_login_state,
    parse_newer_gallery,
    parse_search_page,
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
    "SearchGallery",
    "ShowkeyState",
    "classify_search_body",
    "classify_search_response",
    "cookie_health_loop",
    "get_fixed_preview_thumb_url",
    "parse_favorite_note",
    "parse_gallery_url",
    "parse_login_state",
    "parse_newer_gallery",
    "parse_search_page",
    "probe_cookie_health",
]

logger = logging.getLogger(__name__)

# Ehviewer's Chrome User-Agent. ExHentai may throttle or block requests that do
# not look like a real browser, so we mirror Ehviewer rather than sending a
# custom agent that could get flagged.
EHVIEWER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
)
# Mirror the browser-ish Accept / Accept-Language headers that Ehviewer_CN_SXJ's
# ChromeRequestBuilder sends.  ExHentai's anti-abuse looks at the whole header
# fingerprint, not just the User-Agent; httpx's bare ``*/*`` / missing
# Accept-Language reads as scripted traffic.
EHVIEWER_ACCEPT = (
    "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
)
EHVIEWER_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"

# ExHentai API caps batch operations (gdata, favorites modifygids) at 25 items per request.
EXHENTAI_API_CHUNK_SIZE: int = 25


ALLOWED_EH_DOMAINS = (
    "e-hentai.org",
    "exhentai.org",
    "ehgt.org",
    "hath.network",
)


def _is_allowed_eh_host(host: str, base_url: str | None = None) -> bool:
    if not host:
        return False
    host = host.lower()
    if base_url:
        base_host = (urlparse(base_url).hostname or "").lower()
        if base_host and (host == base_host or host.endswith("." + base_host)):
            return True
    return any(host == domain or host.endswith("." + domain) for domain in ALLOWED_EH_DOMAINS)


# Process-wide limiters. A settings save rebuilds the EhClient and keeps the old
# one alive for a grace period; per-client semaphores would let both clients
# spend a full ExHentai budget at the same time and double our effective
# concurrency. Sharing per running event loop keeps exactly one budget. The
# loop-keyed map keeps test suites (one loop per test) isolated.
_SHARED_LIMITERS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[tuple[str, int], asyncio.Semaphore]
] = weakref.WeakKeyDictionary()


def _shared_limiter(kind: str, limit: int) -> asyncio.Semaphore:
    """Return the loop-wide semaphore for ``kind`` with the given ``limit``."""
    limit = max(1, int(limit))
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Constructed outside a loop (e.g. sync unit tests): no sharing possible.
        return asyncio.Semaphore(limit)
    per_loop = _SHARED_LIMITERS.get(loop)
    if per_loop is None:
        per_loop = {}
        _SHARED_LIMITERS[loop] = per_loop
    key = (kind, limit)
    semaphore = per_loop.get(key)
    if semaphore is None:
        semaphore = asyncio.Semaphore(limit)
        per_loop[key] = semaphore
    return semaphore


def _page_token_from_href(absolute: str) -> str | None:
    """Extract the 10-hex pToken from a viewer URL (mirrors Ehviewer_CN_SXJ).

    Tries the current ``/s/<pToken>/<gid>-<page>`` format, then the legacy
    3-segment format, then the query ``p`` parameter.
    """
    viewer = VIEWER_HREF_RE.search(absolute)
    if viewer:
        return viewer.group("ptoken")
    legacy = PAGE_RE.search(urlparse(absolute).path)
    if legacy:
        return legacy.group("page")
    return parse_qs(urlparse(absolute).query).get("p", [""])[0] or None


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _quota_exceeded_error(response: httpx.Response) -> EhQuotaExceededError:
    status = response.status_code
    return EhQuotaExceededError(
        f"ExHentai rate limited (HTTP {status})",
        status_code=status,
        retry_after=_retry_after_seconds(response),
    )


def _validate_favorites_write_response(
    response: httpx.Response, *, target_favcat: int | None = None
) -> None:
    """Reject HTTP-200 responses that are not a confirmed favorites page.

    ExHentai answers a favorites POST with HTTP 200 even when the session is
    dead, the IP is banned, or the client is being rate limited; following
    redirects means ``raise_for_status`` never fires.  Callers must not treat
    such a body as "favorites changed", so require the favorites page identity
    (folder markers) and, for moves, that the target folder is present.
    """
    if response.status_code in (401, 403) or "login" in str(response.url).lower():
        raise EhClientError("ExHentai authentication is required or expired")
    body = response.text or ""
    if _is_favorites_auth_failure_page(body) or _is_ip_banned_page(body):
        raise EhClientError("ExHentai authentication is required or expired")
    if not body.strip():
        raise EhClientError("ExHentai favorites response was empty")
    favcats = _favorites_page_favcats(body)
    if not favcats:
        raise EhClientError("ExHentai favorites response was not the favorites page")
    if target_favcat is not None and int(target_favcat) not in favcats:
        raise EhClientError(
            f"ExHentai favorites move to folder {int(target_favcat)} was not confirmed"
        )


def _search_response_urls(response: httpx.Response) -> list[str]:
    urls = [str(response.url)]
    urls.extend(str(hist.url) for hist in (response.history or []))
    loc = response.headers.get("location")
    if loc:
        urls.append(str(loc))
    return urls


def classify_search_response(response: httpx.Response) -> str:
    """Classify HTTP-level search failures. ``ok`` means continue to the body."""
    status = response.status_code
    if status in (429, 509):
        return "rate_limited"
    if any("remoteapi.php" in url.lower() for url in _search_response_urls(response)):
        return "challenge"
    if status in (401, 403):
        return "not_logged_in"
    if "login" in str(response.url).lower():
        return "not_logged_in"
    return "ok"


class EhClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_concurrency: int = 6,
    ) -> None:
        self.settings = settings or get_settings()
        self._owned = client is None
        # A single shared limiter for ALL ExHentai page traffic (gallery pages,
        # gdata, favorites) so the many background workers cannot stack dozens
        # of parallel requests and trip ExHentai's anti-abuse.  The limiter is
        # shared per event loop rather than per client: a settings save rebuilds
        # the client and keeps the old one alive for a grace period, and two
        # independent budgets would double the real concurrency.
        self._semaphore = _shared_limiter("page", max(1, max_concurrency))
        # Image downloads go to the H@H network (hath.network) which is a
        # distributed CDN with its own generous limits — mirroring Ehviewer's
        # 32-thread IO pool, we give images their own, higher limiter instead of
        # sharing the page-fetch budget.
        self._image_semaphore = _shared_limiter(
            "image", max(8, max(1, max_concurrency) * 2)
        )
        # Archive (zip) transfers hit the site itself, not H@H, and are long
        # lived; they get their own small budget so concurrent archives cannot
        # bypass the page limits entirely.
        self._archive_semaphore = _shared_limiter("archive", 2)
        # Long-lived transfers currently in flight (images / covers / archives).
        # ``EhClientManager`` waits for this to reach zero before closing a
        # retired client so a settings rebuild cannot kill a running download.
        self._stream_count = 0
        if client is not None:
            self.client = client
        else:
            proxy = self.settings.socks5_proxy or self.settings.http_proxy
            raw_cookies = self.settings.exhentai_cookies
            if isinstance(raw_cookies, dict):
                cookies = dict(raw_cookies)
            elif isinstance(raw_cookies, str) and raw_cookies.strip():
                try:
                    import json as _json

                    parsed = _json.loads(raw_cookies)
                    cookies = dict(parsed) if isinstance(parsed, dict) else {}
                except Exception:  # noqa: BLE001
                    cookies = {}
            else:
                cookies = {}
            # Ehviewer-compatible behaviour flags expressed as ExHentai cookies.
            # uh: load images through the H@H network (y) or not (n).
            # oi: always fetch the original (full) image instead of the resample.
            cookies["uh"] = "y" if self.settings.use_hah else "n"
            cookies["oi"] = "y" if self.settings.download_quality == "original" else "n"
            self.client = httpx.AsyncClient(
                base_url=self.settings.exhentai_base_url.rstrip("/"),
                cookies=cookies,
                proxy=proxy,
                timeout=30.0,
                transport=transport,
                headers={
                    "User-Agent": EHVIEWER_USER_AGENT,
                    "Accept": EHVIEWER_ACCEPT,
                    "Accept-Language": EHVIEWER_ACCEPT_LANGUAGE,
                },
                follow_redirects=True,
            )

        if isinstance(getattr(self.client, "event_hooks", None), dict):
            self.client.event_hooks.setdefault("response", []).append(self._check_redirect_host)

    async def _check_redirect_host(self, response: httpx.Response) -> None:
        """Validate redirect Location host against allowed Eh domains to prevent SSRF."""
        if response.is_redirect:
            location = response.headers.get("Location")
            if location:
                target_url = urljoin(str(response.url), location)
                target_host = (urlparse(target_url).hostname or "").lower()
                if not _is_allowed_eh_host(target_host, self.settings.exhentai_base_url):
                    raise EhClientError(
                        f"Disallowed redirect host in EhClient request: {target_host}"
                    )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owned:
            await self.client.aclose()

    @property
    def in_flight_requests(self) -> int:
        """Number of long-lived transfers (image / cover / archive) still running."""
        return self._stream_count

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        t_wait_start = time.perf_counter()
        async with self._semaphore:
            wait_elapsed = time.perf_counter() - t_wait_start
            observe_histogram("gv_ehclient_semaphore_wait_seconds", wait_elapsed, {"type": "page"})
            t_req_start = time.perf_counter()
            try:
                return await self.client.request(method, url, **kwargs)
            except httpx.HTTPStatusError as exc:
                # ``_request`` normally returns 4xx/5xx responses and callers use
                # ``_raise_for_status``; wrapping here keeps the "EhClient only
                # raises EhClientError" contract if a transport/wrapper raises.
                raise self._status_error(exc.response) from exc
            finally:
                req_elapsed = time.perf_counter() - t_req_start
                observe_histogram("gv_ehclient_request_duration_seconds", req_elapsed, {"method": method})

    @staticmethod
    def _status_error(response: httpx.Response) -> EhClientError:
        """Classify a non-2xx response (quota exhaustion vs. generic failure)."""
        status = response.status_code
        if status in (429, 509):
            return _quota_exceeded_error(response)
        return EhClientError(f"ExHentai returned HTTP {status}")

    def _raise_for_status(
        self, response: httpx.Response, *, gallery_404: bool = False
    ) -> None:
        """Turn HTTP status failures into ``EhClientError`` subclasses."""
        status = response.status_code
        if status in (401, 403) or "login" in str(response.url).lower():
            raise EhClientError("ExHentai authentication is required or expired")
        if status in (429, 509):
            raise _quota_exceeded_error(response)
        if status < 400:
            return
        if status == 404 and gallery_404:
            try:
                path = response.request.url.path
            except RuntimeError:
                path = ""
            if path.startswith("/g/"):
                raise GalleryGoneError("gallery does not exist on ExHentai (404)")
        raise self._status_error(response)

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._request("GET", url, **kwargs)
            if (
                response.status_code in (401, 403)
                or "login" in str(response.url).lower()
                or _is_auth_failure_page(response.text)
                or _is_ip_banned_page(response.text)
            ):
                raise EhClientError("ExHentai authentication is required or expired")
            self._raise_for_status(response, gallery_404=True)
            # Buffer the body inside the try so a connection reset while reading
            # is wrapped as EhClientError below instead of leaking a raw
            # RemoteProtocolError to the download worker.
            await response.aread()
            return response
        except httpx.RequestError as exc:
            # Covers TimeoutException, ConnectError, ReadError,
            # RemoteProtocolError, ProxyError — every transient transport
            # failure must surface as EhClientError so callers retry instead of
            # treating a dead proxy/DNS blip as a permanent per-gallery failure.
            logger.warning("ExHentai request failed", extra=log_extra(error=type(exc).__name__))
            raise EhClientError("ExHentai request failed") from exc
        except httpx.HTTPStatusError as exc:
            # ``_request`` already converts these; kept as a defensive catch so a
            # raw httpx status error never escapes the EhClient contract.
            status = exc.response.status_code
            logger.warning(
                "ExHentai returned HTTP error", extra=log_extra(status=status)
            )
            raise self._status_error(exc.response) from exc

    async def check_login(self) -> tuple[str, str]:
        """Probe ExHentai and return ``(state, detail)``.

        ``state`` is one of ``ok`` / ``not_logged_in`` / ``no_exhentai_access`` /
        ``ip_banned`` / ``failed``; ``detail`` carries the HTTP status or exception type for the
        failure message. Probes ``/uconfig.php`` (a member-only settings page):
        every session state answers HTTP 200, but the body distinguishes them —
        a full page for a valid session, ``expired login session`` for a dead
        one, and an empty/blank body when no cookies or no access are present.
        Retries once on transport errors or empty/blank 200 responses.
        """
        last_error: Exception | None = None
        last_response: httpx.Response | None = None
        for _ in range(2):
            try:
                response = await self._request("GET", "/uconfig.php")
            except httpx.RequestError as exc:
                last_error = exc
                last_response = None
                continue
            last_response = response
            if response.status_code in (401, 403) or "login" in str(response.url).lower():
                return "not_logged_in", f"HTTP {response.status_code}"
            body = response.text
            if _is_ip_banned_page(body):
                return "ip_banned", f"HTTP {response.status_code}"
            if _is_auth_failure_page(body):
                return "no_exhentai_access", f"HTTP {response.status_code}"
            if not body or not body.strip():
                continue
            host = (
                urlparse(str(response.url)).hostname
                or urlparse(self.settings.exhentai_base_url).hostname
            )
            return (
                parse_login_state(body, host=host),
                f"HTTP {response.status_code}",
            )
        if last_response is not None:
            host = (
                urlparse(str(last_response.url)).hostname
                or urlparse(self.settings.exhentai_base_url).hostname
            )
            state = "no_exhentai_access" if _is_exhentai_org_host(host) else "failed"
            return state, f"HTTP {last_response.status_code}"
        return "failed", type(last_error).__name__

    async def probe_challenge(self, sample_path: str = "/") -> bool:
        """Probe ExHentai to check if the 302 anti-abuse challenge has cleared."""
        try:
            response = await self._get(sample_path)
            url_str = str(response.url)
            if "remoteapi.php" in url_str or "poni=no" in url_str:
                return False
            return not (sample_path.startswith("/g/") and not str(response.url.path).startswith("/g/"))
        except Exception:  # noqa: BLE001
            return False

    async def fetch_gallery_metadata(self, gid: int, token: str) -> GalleryData:
        """Fetch only gallery metadata; tag sync must not enumerate or download pages."""
        response = await self._get(f"/g/{int(gid)}/{token}/")
        # Mirror fetch_gallery's anti-abuse challenge guard: ExHentai sometimes
        # 302s through remoteapi.php and lands on "/" with no content. The
        # cookie is still valid — treat as transient, not "gone".
        if not str(response.url.path).startswith("/g/"):
            raise EhChallengeError("ExHentai is challenging this client (temporary anti-abuse)")
        body = response.text
        if _is_auth_failure_page(body) or _is_ip_banned_page(body):
            raise EhClientError("ExHentai authentication is required or expired")
        if not body or not body.strip():
            raise EhClientError("ExHentai returned empty gallery page (temporary anti-abuse)")
        title, title_jpn = _parse_gallery_titles(body)
        tags = _parse_tags(body)
        newer = parse_newer_gallery(body, int(gid))
        if not title and newer is None:
            # ExHentai answers non-existent / deleted galleries with a tiny
            # 200 page that has no title (or a real 404). But an empty/challenged
            # page also has no title — the guards above already filtered those, so
            # this remaining case is a genuine gone gallery.
            raise GalleryGoneError("gallery does not exist on ExHentai")
        return GalleryData(
            int(gid), token, title, [], tags, _parse_category(body), title_jpn,
            _parse_file_size(body), newer,
        )

    async def fetch_gallery(
        self,
        gid: int | str,
        token: str | None = None,
        max_pages: int | None = None,
        *,
        resolve_urls: bool = True,
    ) -> GalleryData:
        if token is None:
            gid, token = parse_gallery_url(str(gid), self.settings.exhentai_base_url)
        base = f"/g/{int(gid)}/{token}/"
        response = await self._get(base)
        # ExHentai's remoteapi.php anti-bot challenge: the /g/ URL 302s through
        # forums.e-hentai.org/remoteapi.php?ex=… and lands on the site root
        # (…/?poni=no). The session cookie is fine — the IP is being
        # rate-challenged temporarily. Callers treat this as retryable.
        if not str(response.url.path).startswith("/g/"):
            raise EhChallengeError("ExHentai is challenging this client (temporary anti-abuse)")
        body = response.text
        title, title_jpn = _parse_gallery_titles(body)
        newer = parse_newer_gallery(body, int(gid))
        if newer is not None:
            return GalleryData(
                int(gid),
                token,
                title,
                [],
                _parse_tags(body),
                _parse_category(body),
                title_jpn,
                _parse_file_size(body),
                newer,
            )
        # ExHentai lists roughly 20 page links per gallery page and paginates
        # long galleries with ?p=N.  Enumerate every gallery sub-page so whole
        # galleries are downloaded, not just the first screenful.
        page_hrefs: list[str] = []
        seen: set[str] = set()
        gid_pattern = re.compile(rf"/s/[0-9a-fA-F]+/{int(gid)}-\d+", re.IGNORECASE)

        def _collect_hrefs(page_body: str, limit: int | None = None) -> int:
            """Collect viewer hrefs from one gallery page; returns count added."""
            collected = 0
            for href in re.findall(
                r'<a[^>]+href=["\']([^"\']+)["\']', page_body, re.IGNORECASE
            ):
                if gid_pattern.search(href) and href not in seen:
                    seen.add(href)
                    page_hrefs.append(href)
                    collected += 1
            if limit is not None and limit > 0 and len(page_hrefs) >= limit:
                del page_hrefs[limit:]
                seen.clear()
                seen.update(page_hrefs)
            return collected

        # Size the enumeration with gdata's filecount so the gallery sub-pages
        # can be fetched concurrently instead of serially (a 255-page gallery
        # previously walked 13 pages one at a time).
        estimate = 0
        try:
            gdata = await self.fetch_gmetadata([(int(gid), token)])
            info = gdata.get(int(gid)) or {}
            estimate = int(info.get("file_count") or 0)
        except Exception:  # noqa: BLE001 - fall back to sequential enumeration
            estimate = 0
        gallery_pages = max(1, (estimate + 19) // 20) if estimate > 0 else 0
        _collect_hrefs(body, max_pages)
        start = 1
        truncated_by_limit = (
            max_pages is not None and max_pages > 0 and len(page_hrefs) >= max_pages
        )
        if gallery_pages > 1 and not truncated_by_limit:
            offsets = list(range(1, min(gallery_pages, 512)))

            async def _fetch_page(offset: int) -> tuple[int, str]:
                page_response = await self._get(f"{base}?p={offset}")
                if not str(page_response.url.path).startswith("/g/"):
                    raise EhChallengeError("ExHentai is challenging this client (temporary anti-abuse)")
                return offset, page_response.text

            fetched: dict[int, str] = {}
            try:
                for offset, text in await asyncio.gather(
                    *(_fetch_page(o) for o in offsets)
                ):
                    fetched[offset] = text
            except EhChallengeError:
                raise
            except Exception:  # noqa: BLE001 - redo the range serially below
                fetched = {}
            if fetched:
                for offset in sorted(fetched):
                    if _collect_hrefs(fetched[offset], max_pages) == 0:
                        break
                    if max_pages is not None and max_pages > 0 and len(page_hrefs) >= max_pages:
                        break
                # The gdata filecount may be stale or undercount: keep walking
                # from the end of the concurrent batch until a page is empty.
                start = max(offsets) + 1
        if not truncated_by_limit:
            # Serial tail walk. Fix for stale gdata under-report: the old
            # ``gallery_pages + 2`` guard truncated long galleries when gdata
            # file_count was outdated (e.g. actual 255 pages but gdata said 20
            # => only 2 extra pages walked). Now walk until two consecutive
            # empty pages, which tolerates a single glitched page but still
            # terminates, and is unbounded when estimate==0. A hard 5000-offset
            # cap (~100k images) prevents an infinite loop if the server echoes
            # content.
            offset = start
            empty_streak = 0
            while True:
                if offset > 5000:
                    break
                page_response = await self._get(f"{base}?p={offset}")
                if not str(page_response.url.path).startswith("/g/"):
                    raise EhChallengeError("ExHentai is challenging this client (temporary anti-abuse)")
                collected = _collect_hrefs(page_response.text, max_pages)
                if collected == 0:
                    empty_streak += 1
                    if empty_streak >= 2:
                        break
                    # One empty after we have passed estimate+2 could be real tail,
                    # but require two empties to be safe against a transient gap.
                    offset += 1
                    continue
                empty_streak = 0
                if max_pages is not None and max_pages > 0 and len(page_hrefs) >= max_pages:
                    break
                offset += 1
        if not page_hrefs:
            raise EhParseError("gallery HTML did not contain a title and page links")
        if resolve_urls:
            pages = await self._resolve_gallery_pages(int(gid), str(response.url), page_hrefs)
        else:
            # Lazy mode: return index + viewer URL + pToken only, leaving
            # image_url empty.  The downloader resolves each page's URL right
            # before fetching (see resolve_page) so a long download never
            # serves a keystamp that has already expired.
            pages = [
                GalleryPageData(
                    index,
                    urljoin(str(response.url), html.unescape(href)),
                    _page_token_from_href(
                        urljoin(str(response.url), html.unescape(href))
                    ),
                )
                for index, href in enumerate(page_hrefs)
            ]
        if not title:
            raise EhParseError("gallery HTML did not contain a title and page links")
        tags = _parse_tags(body)
        return GalleryData(
            int(gid), token, title, pages, tags, _parse_category(body), title_jpn
        )

    async def _resolve_gallery_pages(
        self, gid: int, base_url: str, page_hrefs: list[str]
    ) -> list[GalleryPageData]:
        """Resolve every viewer href to its image URL (mirrors Ehviewer_CN_SXJ).

        The first page is resolved via full HTML so its ``showkey`` is available
        for the lightweight ``showpage`` API on the remaining pages.  All pages
        resolve concurrently (bounded by the shared ExHentai semaphore): serial
        resolution of a 255-page gallery took minutes.
        """
        showkey = ShowkeyState()

        async def _resolve_page_html(href: str) -> GalleryPageData:
            """Resolve one viewer page from its full HTML (also yields the showkey)."""
            absolute = urljoin(base_url, html.unescape(href))
            p_token = _page_token_from_href(absolute)
            page_response = await self._get(absolute)
            body = page_response.text
            image_match = None
            for image_tag in IMAGE_RE.finditer(body):
                tag = image_tag.group(0)
                if re.search(r'\bid=["\']img["\']', tag, re.IGNORECASE):
                    image_match = re.search(r'\bsrc=["\']([^"\']+)["\']', tag, re.IGNORECASE)
                    if image_match:
                        break
            if not image_match:
                raise EhClientError(f"viewer page has no image: {absolute}")
            image_url = urljoin(str(page_response.url), html.unescape(image_match.group(1)))
            origin_match = re.search(
                r'<a[^>]+href=["\']([^"\']+)fullimg([^"\']+)["\']', body, re.IGNORECASE
            )
            nl_match = re.search(r"nl\(\s*['\"](.*?)['\"]\s*\)", body)
            showkey_match = SHOWKEY_RE.search(body)
            if showkey_match:
                # Always refresh from the latest viewer page: a showkey expires
                # after a while, so HTML fallbacks must re-seed it or every
                # remaining page pays for a failing showpage call plus its HTML
                # fallback.
                showkey.value = showkey_match.group(1)
            origin_url = (
                urljoin(str(page_response.url), html.unescape(origin_match.group(1)))
                + "fullimg"
                + html.unescape(origin_match.group(2))
                if origin_match
                else None
            )
            return GalleryPageData(
                -1,
                absolute,
                p_token or "",
                image_url,
                origin_url,
                html.unescape(nl_match.group(1)) if nl_match else None,
            )

        async def _resolve_page_api(href: str) -> GalleryPageData:
            """Resolve one viewer page through the lightweight ``showpage`` API.

            Mirrors Ehviewer_CN_SXJ's ``getGalleryPageApi``: one POST to api.php
            returns JSON ``{i3, i6, i7}`` carrying the resample URL, the H@H
            skip key and the original (fullimg) URL — far smaller and stabler to
            parse than the whole viewer-page HTML.  Requires the pToken from the
            gallery-page preview links plus a ``showkey`` (from the first viewer
            page); falls back to HTML on any failure.
            """
            absolute = urljoin(base_url, html.unescape(href))
            viewer = VIEWER_HREF_RE.search(absolute)
            if not viewer:
                return await _resolve_page_html(href)
            p_token = viewer.group("ptoken")
            page = int(viewer.group("page"))
            if not showkey.value:
                return await _resolve_page_html(href)
            try:
                info = await self._showpage(gid, page, p_token, showkey.value, absolute)
            except EhClientError:
                # API hiccup (stale showkey, throttled, changed markup): fall back
                # to the full HTML path, which re-seeds showkey if needed.
                return await _resolve_page_html(href)
            return GalleryPageData(
                -1,
                absolute,
                p_token,
                info["image_url"],
                info["origin_url"],
                info["skip_hath_key"],
            )

        if page_hrefs:
            first = await _resolve_page_html(page_hrefs[0])
            pages = [first]
            if len(page_hrefs) > 1:
                pages.extend(
                    await asyncio.gather(
                        *(_resolve_page_api(h) for h in page_hrefs[1:])
                    )
                )
        return [
            GalleryPageData(
                index, r.url, r.token, r.image_url, r.origin_url, r.skip_hath_key
            )
            for index, r in enumerate(pages)
        ]

    async def resolve_page(
        self,
        gid: int,
        page: GalleryPageData,
        showkey: ShowkeyState | None = None,
        *,
        skip_hath: bool = False,
    ) -> GalleryPageData:
        """Resolve one page's fresh image URLs right before downloading.

        Called by the downloader per page so the keystamp is never stale (a
        long gallery would otherwise serve URLs signed 20 minutes earlier,
        which H@H nodes reject with 403).  Prefers the lightweight showpage
        API when a showkey is known and falls back to full HTML otherwise.
        """
        if showkey is None:
            showkey = ShowkeyState()
        if skip_hath:
            if not page.skip_hath_key:
                page = await self._resolve_page_from_html(gid, page, showkey)
            if page.skip_hath_key:
                parsed = urlparse(page.url)
                query_pairs = [
                    (k, v)
                    for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                    if k != "nl"
                ]
                query_pairs.append(("nl", page.skip_hath_key))
                target_url = urlunparse(
                    (
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        parsed.params,
                        urlencode(query_pairs),
                        parsed.fragment,
                    )
                )
                target_page = replace(page, url=target_url)
                return await self._resolve_page_from_html(gid, target_page, showkey)
        absolute = page.url
        viewer = VIEWER_HREF_RE.search(absolute)
        p_token = viewer.group("ptoken") if viewer else (page.token or "")
        page_num = int(viewer.group("page")) if viewer else page.index + 1
        if showkey.value:
            try:
                info = await self._showpage(
                    gid, page_num, p_token, showkey.value, absolute
                )
            except EhClientError:
                # Stale showkey / throttled API: fall back to HTML, which
                # re-seeds the showkey (same as fetch_gallery does).
                return await self._resolve_page_from_html(gid, page, showkey)
            return GalleryPageData(
                page.index,
                absolute,
                p_token,
                info["image_url"],
                info["origin_url"],
                info["skip_hath_key"],
            )
        return await self._resolve_page_from_html(gid, page, showkey)

    async def _resolve_page_from_html(
        self, gid: int, page: GalleryPageData, showkey: ShowkeyState | None = None
    ) -> GalleryPageData:
        """Full-HTML resolution for a single page (mirrors ``_resolve_page_html``).

        Used by ``resolve_page`` when no showkey is available or the showpage
        API rejects.  Reuses the fresh viewer HTML so the image URL, origin URL
        and H@H skip key are all current.
        """
        absolute = page.url
        p_token = _page_token_from_href(absolute)
        page_response = await self._get(absolute)
        body = page_response.text
        image_match = None
        for image_tag in IMAGE_RE.finditer(body):
            tag = image_tag.group(0)
            if re.search(r'\bid=["\']img["\']', tag, re.IGNORECASE):
                image_match = re.search(r'\bsrc=["\']([^"\']+)["\']', tag, re.IGNORECASE)
                if image_match:
                    break
        if not image_match:
            raise EhClientError(f"viewer page has no image: {absolute}")
        image_url = urljoin(str(page_response.url), html.unescape(image_match.group(1)))
        origin_match = re.search(
            r'<a[^>]+href=["\']([^"\']+)fullimg([^"\']+)["\']', body, re.IGNORECASE
        )
        nl_match = re.search(r"nl\(\s*['\"](.*?)['\"]\s*\)", body)
        showkey_match = SHOWKEY_RE.search(body)
        if showkey_match and showkey is not None:
            showkey.value = showkey_match.group(1)
        origin_url = (
            urljoin(str(page_response.url), html.unescape(origin_match.group(1)))
            + "fullimg"
            + html.unescape(origin_match.group(2))
            if origin_match
            else None
        )
        return GalleryPageData(
            page.index,
            absolute,
            p_token or "",
            image_url,
            origin_url,
            html.unescape(nl_match.group(1)) if nl_match else None,
        )

    async def _showpage(
        self,
        gid: int,
        page: int,
        p_token: str,
        showkey: str,
        referer: str | None = None,
    ) -> dict[str, str]:
        """Resolve one page's image URLs via the ExHentai ``showpage`` API.

        ``page`` is 1-based.  Returns ``{image_url, origin_url, skip_hath_key}``
        exactly like parsing the viewer HTML would, but from a small JSON body.
        ``referer`` should be the gallery viewer URL this call originates from —
        ExHentai expects the browser-like Referer + Origin on its JSON API.
        """
        payload = {
            "method": "showpage",
            "gid": int(gid),
            "page": int(page),
            "imgkey": p_token,
            "showkey": showkey,
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if referer:
            headers["Referer"] = referer
        headers["Origin"] = self.settings.exhentai_base_url.rstrip("/")
        try:
            response = await self._request(
                "POST",
                "/api.php",
                json=payload,
                headers=headers,
            )
        except httpx.RequestError as exc:
            # Raw transport errors (e.g. ConnectTimeout) must surface as
            # EhClientError: callers treat it as retryable-with-backoff, whereas
            # a leaked httpx exception would retry immediately without the 30s
            # challenge backoff.
            logger.warning(
                "ExHentai showpage request failed",
                extra=log_extra(error=type(exc).__name__),
            )
            raise EhClientError("ExHentai request failed") from exc
        self._raise_for_status(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise EhClientError("ExHentai showpage response was not JSON") from exc
        error = body.get("error")
        if error:
            raise EhClientError(f"ExHentai showpage error: {error}")
        i3 = body.get("i3") or ""
        i6 = body.get("i6") or ""
        i7 = body.get("i7")
        image_match = SHOWPAGE_IMAGE_RE.search(i3)
        if not image_match:
            raise EhClientError("ExHentai showpage returned no image URL")
        image_url = urljoin(str(response.url), html.unescape(image_match.group(1)))
        skip_match = SHOWPAGE_SKIP_KEY_RE.search(i6)
        skip_hath_key = html.unescape(skip_match.group(1)) if skip_match else None
        origin_url = None
        # Prefer the i7 ``fullimg`` link (the original-quality URL), matching the
        # HTML path and Ehviewer_CN_SXJ's preference for originImageUrl.  The i6
        # prompt URL is only a fallback when the origin link is missing.
        if i7 is not None:
            origin_match = SHOWPAGE_ORIGIN_RE.search(i7)
            if origin_match:
                origin_url = urljoin(
                    str(response.url),
                    html.unescape(origin_match.group(1))
                    + "fullimg"
                    + html.unescape(origin_match.group(2)),
                )
        if origin_url is None:
            prompt_match = SHOWPAGE_ORIGIN_PROMPT_RE.search(i6)
            if prompt_match:
                origin_url = urljoin(str(response.url), html.unescape(prompt_match.group(1)))
        return {
            "image_url": image_url,
            "origin_url": origin_url,
            "skip_hath_key": skip_hath_key,
        }

    async def fetch_favorites(
        self,
        favcat: int,
        progress: Callable[[int], object] | None = None,
        *,
        max_pages: int | None = None,
    ) -> FavoriteItems:
        """Fetch every gallery in a favorite folder, following ExHentai paging.

        ExHentai favorites are paginated with a ``next`` cursor embedded in the
        page (``var nexturl="...?favcat=N&next=gid-timestamp"``) rather than a
        ``page`` number; walking only the first page silently drops the tail of
        a large folder.  ``progress`` (if given) is called with the number of
        galleries collected so far after every page.

        ``max_pages`` bounds the walk (``1`` is a single first-page probe used
        by the scheduled skip heuristic).  The header count is still parsed, so
        the returned object reports ``truncated`` honestly even for a probe.

        The returned :class:`FavoriteItems` records whether an empty result is
        confirmed by the folder header (``confirmed_empty``) and whether paging
        stopped short of the header count (``truncated``), so callers can avoid
        deleting local favorites on a partial or unparseable page.
        """
        result = FavoriteItems()
        seen: set[int] = set()
        header_counts: dict[int, int] | None = None
        url = "/favorites.php"
        params: dict[str, object] = {"favcat": int(favcat)}
        pages = 0
        while True:
            response = await self._get(url, params=params)
            # Identity check: a dead session or an anti-abuse redirect can land
            # on a generic page that still carries ``/g/`` links. Parsing it
            # would import homepage/search gids as favorites (and let the
            # pruner delete real rows), so require the favorites route, and
            # never treat a login/logout body as "empty favorites".
            final_path = urlparse(str(response.url)).path.rstrip("/")
            if final_path != "/favorites.php":
                raise EhClientError(
                    f"ExHentai favorites request left the favorites page ({final_path or '/'})"
                )
            if _is_favorites_auth_failure_page(response.text):
                raise EhClientError("ExHentai authentication is required or expired")
            if header_counts is None:
                header_counts = _parse_favorite_counts(response.text)
            # The cover thumbnail lives in a SEPARATE link (the glthumb cell)
            # from the title link the loop below matches, so map gid -> thumb
            # from the whole page once and look it up per item.
            thumbs: dict[int, str] = {}
            for tm in re.finditer(
                r'<a[^>]+href=["\']([^"\']*(?:/g/|/gallery/)[^"\']*)["\'][^>]*>'
                r'\s*<img[^>]+src=["\']([^"\']+)["\']',
                response.text,
                re.IGNORECASE | re.DOTALL,
            ):
                try:
                    tgid, _ = parse_gallery_url(tm.group(1), self.settings.exhentai_base_url)
                except ValueError:
                    continue
                thumbs[tgid] = html.unescape(tm.group(2))
            items: list[FavoriteData] = []
            for href, label in re.findall(
                r'<a[^>]+href=["\']([^"\']*(?:/g/|/gallery/)[^"\']*)["\'][^>]*>(?![^<]*<img)(.*?)</a>',
                response.text,
                re.IGNORECASE | re.DOTALL,
            ):
                try:
                    gid, token = parse_gallery_url(href, self.settings.exhentai_base_url)
                except ValueError:
                    continue
                if gid in seen:
                    continue
                seen.add(gid)
                # ExHentai nests the whole tag table inside the title <a>, so
                # only the <div class="glink"> holds the actual title.
                glink = re.search(
                    r'<div[^>]*class=["\']glink["\'][^>]*>(.*?)</div>',
                    label,
                    re.IGNORECASE | re.DOTALL,
                )
                title = _text(glink.group(1)) if glink else _text(label)
                snippet = _search_item_window(response.text, gid, token)
                items.append(
                    FavoriteData(
                        gid,
                        token,
                        title,
                        urljoin(str(response.url), href),
                        thumbs.get(gid),
                        parse_favorite_note(snippet, gid),
                    )
                )
            if not items:
                break
            result.extend(items)
            if progress is not None:
                progress(len(result))
            pages += 1
            if max_pages is not None and pages >= max_pages:
                break
            next_url = html.unescape(_favorites_next_url(response.text))
            if not next_url:
                break
            parsed = urlparse(next_url)
            url = parsed.path or "/favorites.php"
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        # Only the header count can confirm an empty folder or a short listing;
        # without it the result is "unknown" and callers must not prune on it.
        cloud_count = header_counts.get(int(favcat)) if header_counts else None
        result.cloud_count = cloud_count
        result.confirmed_empty = not result and cloud_count == 0
        result.truncated = cloud_count is not None and len(result) < cloud_count
        return result

    async def search_galleries(
        self,
        *,
        q: str = "",
        f_cats: int | None = None,
        min_rating: float | None = None,
        next_cursor: str | None = None,
        list_type: str = "search",
        tl: int | None = None,
    ) -> EhSearchResult:
        """Fetch one ExHentai listing (cursor, not ``page=N``).

        ``list_type``: ``search`` (``/``), ``popular`` (``/popular``),
        ``watched`` (``/watched``), ``toplist`` (``/toplist.php?tl=``).
        Toplist ``tl`` values match the site: 11 yesterday / 12 month /
        13 year / 15 all-time.
        """
        kind = (list_type or "search").strip().lower()
        if kind not in {"search", "popular", "watched", "toplist"}:
            raise ValueError("invalid list")
        params: dict[str, object] = {}
        path = "/"
        if kind == "popular":
            path = "/popular"
        elif kind == "watched":
            path = "/watched"
        elif kind == "toplist":
            path = "https://e-hentai.org/toplist.php"
            tl_value = 15 if tl is None else int(tl)
            if tl_value not in {11, 12, 13, 15}:
                raise ValueError("invalid toplist tl")
            params["tl"] = tl_value
        if kind in {"search", "watched"} and q and str(q).strip():
            params["f_search"] = str(q).strip()
        if kind == "search" and f_cats is not None:
            params["f_cats"] = int(f_cats)
        cur_p = 0
        if next_cursor:
            if kind == "toplist":
                if not _TOPLIST_CURSOR_RE.fullmatch(str(next_cursor)) or not (
                    0 <= int(next_cursor) < 200
                ):
                    raise ValueError("invalid next cursor")
                cur_p = int(next_cursor)
                if cur_p > 0:
                    params["p"] = cur_p
            else:
                if not _NEXT_CURSOR_RE.fullmatch(str(next_cursor)):
                    raise ValueError("invalid next cursor")
                params["next"] = str(next_cursor)
        if kind in {"search", "watched"} and min_rating is not None:
            srdd = max(2, min(5, int(min_rating)))
            params["advsearch"] = 1
            params["f_sr"] = "on"
            params["f_srdd"] = srdd
        req_kwargs: dict[str, Any] = {"params": params}
        if kind == "toplist":
            raw_cookies = getattr(self.settings, "exhentai_cookies", None)
            cookies: dict[str, str] = {}
            if isinstance(raw_cookies, dict):
                cookies = {str(k): str(v) for k, v in raw_cookies.items()}
            elif isinstance(raw_cookies, str) and raw_cookies.strip():
                try:
                    import json as _json

                    parsed = _json.loads(raw_cookies)
                    if isinstance(parsed, dict):
                        cookies = {str(k): str(v) for k, v in parsed.items()}
                except Exception:  # noqa: BLE001, S110
                    pass
            if cookies:
                cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
                req_kwargs["headers"] = {"Cookie": cookie_str}
        try:
            response = await self._request("GET", path, **req_kwargs)
        except httpx.RequestError as exc:
            logger.warning("ExHentai search failed", extra=log_extra(error=type(exc).__name__))
            raise EhClientError("ExHentai request failed") from exc
        state = classify_search_response(response)
        if state != "ok":
            return EhSearchResult(items=[], next_cursor=None, state=state)
        if response.status_code >= 400:
            raise EhClientError(f"ExHentai returned HTTP {response.status_code}")
        try:
            await response.aread()
        except httpx.RequestError as exc:
            raise EhClientError("ExHentai request failed") from exc
        body = response.text
        state = classify_search_body(body)
        if state != "ok":
            return EhSearchResult(items=[], next_cursor=None, state=state)
        items, nxt = parse_search_page(
            body, "https://e-hentai.org" if kind == "toplist" else str(self.settings.exhentai_base_url)
        )
        if kind == "toplist":
            nxt = _toplist_next_cursor(body, cur_p)
        if items:
            return EhSearchResult(items=items, next_cursor=nxt, state="ok")
        if next_cursor:
            return EhSearchResult(items=[], next_cursor=None, state="ok")
        if re.search(r"No hits found", body, re.IGNORECASE):
            return EhSearchResult(items=[], next_cursor=None, state="empty")
        if 'name="f_search"' in body or "itg" in body.lower():
            return EhSearchResult(items=[], next_cursor=None, state="empty")
        return EhSearchResult(items=[], next_cursor=None, state="challenge")

    async def fetch_favorite_categories(self) -> dict[int, str]:
        response = await self._get("/favorites.php")
        return _parse_favorite_categories(response.text)

    async def fetch_favorite_counts(self) -> dict[int, int] | None:
        """Current per-folder gallery counts from one favorites.php request.

        Returns ``None`` when the page header could not be parsed (login wall,
        redirect, or markup drift). A parsed mapping is authoritative and may
        legitimately contain zeros (``{0: 0}`` = the folder is empty).
        """
        response = await self._get("/favorites.php")
        final_path = urlparse(str(response.url)).path.rstrip("/")
        if final_path != "/favorites.php":
            raise EhClientError(
                f"ExHentai favorites counts request left the favorites page "
                f"({final_path or '/'})"
            )
        if _is_favorites_auth_failure_page(response.text):
            raise EhClientError("ExHentai authentication is required or expired")
        return _parse_favorite_counts(response.text)

    async def remove_favorites(self, gids: list[int]) -> list[int]:
        """Remove galleries from ExHentai favorites (across all folders).

        Mirrors Ehviewer_CN_SXJ: POST /favorites.php with ``ddact=delete`` and
        one ``modifygids[]`` entry per gid.  ExHentai caps each request at 25
        gids, so larger lists are chunked; a failed chunk is retried once per
        gid so one bad gallery cannot block the rest.  Returns the list of gids
        that could not be removed (empty on full success).
        """
        if not gids:
            return []
        failed: list[int] = []

        async def _post(gids_batch: list[int]) -> None:
            form = {
                "ddact": "delete",
                "apply": "Apply",
                "modifygids[]": [str(int(g)) for g in gids_batch],
            }
            response = await self._request(
                "POST",
                "/favorites.php",
                data=form,
                headers={
                    "Referer": urljoin(str(self.client.base_url), "/favorites.php"),
                    "Origin": self.settings.exhentai_base_url.rstrip("/"),
                },
            )
            self._raise_for_status(response)
            _validate_favorites_write_response(response)

        for chunk in (
            gids[i : i + EXHENTAI_API_CHUNK_SIZE]
            for i in range(0, len(gids), EXHENTAI_API_CHUNK_SIZE)
        ):
            try:
                await _post(chunk)
            except EhClientError:
                # Auth expiry is not a per-gallery failure: propagate so the
                # caller can surface a dead session instead of swallowing it.
                raise
            except Exception as exc:  # noqa: BLE001 - retry each gid on its own
                logger.info(
                    "batch favorites remove failed; retrying per gid",
                    extra=log_extra(chunk_size=len(chunk), error=str(exc)),
                )
                for gid in chunk:
                    try:
                        await _post([gid])
                    except Exception as single_exc:  # noqa: BLE001 - surface per-gid failures
                        logger.warning(
                            "per-gid favorites remove failed on cloud",
                            extra=log_extra(gid=gid, error=str(single_exc)),
                        )
                        failed.append(gid)
        return failed

    async def move_favorites(self, gids: list[int], target_favcat: int) -> list[int]:
        """Move galleries to an ExHentai favorite folder (target_favcat 0..9).

        Mirrors favorites.php batch action: POST /favorites.php with
        ``ddact=fav{target_favcat}``, ``apply=Apply``, and ``modifygids[]``.
        Chunked at 25 gids per request.  Returns the list of gids that could
        not be moved (empty on full success).
        """
        if not gids:
            return []
        if not (0 <= target_favcat <= 9):
            raise ValueError("target_favcat must be between 0 and 9")
        failed: list[int] = []

        async def _post(gids_batch: list[int]) -> None:
            form = {
                "ddact": f"fav{int(target_favcat)}",
                "apply": "Apply",
                "modifygids[]": [str(int(g)) for g in gids_batch],
            }
            response = await self._request(
                "POST",
                "/favorites.php",
                data=form,
                headers={
                    "Referer": urljoin(str(self.client.base_url), "/favorites.php"),
                    "Origin": self.settings.exhentai_base_url.rstrip("/"),
                },
            )
            self._raise_for_status(response)
            _validate_favorites_write_response(response, target_favcat=target_favcat)

        for chunk in (
            gids[i : i + EXHENTAI_API_CHUNK_SIZE]
            for i in range(0, len(gids), EXHENTAI_API_CHUNK_SIZE)
        ):
            try:
                await _post(chunk)
            except EhClientError:
                raise
            except Exception as exc:  # noqa: BLE001 - retry each gid on its own
                logger.info(
                    "batch favorites move failed; retrying per gid",
                    extra=log_extra(
                        chunk_size=len(chunk), target_favcat=target_favcat, error=str(exc)
                    ),
                )
                for gid in chunk:
                    try:
                        await _post([gid])
                    except Exception as single_exc:  # noqa: BLE001 - surface per-gid failures
                        logger.warning(
                            "per-gid favorites move failed on cloud",
                            extra=log_extra(
                                gid=gid, target_favcat=target_favcat, error=str(single_exc)
                            ),
                        )
                        failed.append(gid)
        return failed

    async def add_favorite(
        self, gid: int, token: str, favcat: int, note: str = ""
    ) -> None:
        """Add a single gallery to an ExHentai favorite folder (favcat 0..9).

        Mirrors EhEngine.addFavorites: POST /gallerypopups.php?gid={gid}&t={token}&act=addfav
        with favcat={favcat}, favnote={note}, update=1, submit=Apply Changes.
        """
        if not (0 <= favcat <= 9):
            raise ValueError("favcat must be between 0 and 9")
        form = {
            "favcat": str(int(favcat)),
            "favnote": note or "",
            "update": "1",
            "submit": "Apply Changes",
        }
        url = f"/gallerypopups.php?gid={int(gid)}&t={token}&act=addfav"
        response = await self._request(
            "POST",
            url,
            data=form,
            headers={
                "Referer": urljoin(str(self.client.base_url), url),
                "Origin": self.settings.exhentai_base_url.rstrip("/"),
            },
        )
        if (
            response.status_code in (401, 403)
            or "login" in str(response.url).lower()
            or _is_auth_failure_page(response.text)
            or _is_ip_banned_page(response.text)
        ):
            raise EhClientError("ExHentai authentication is required or expired")
        self._raise_for_status(response)

    async def add_favorites(
        self, items: list[tuple[int, str]], favcat: int, note: str = ""
    ) -> list[int]:
        """Add multiple galleries to an ExHentai favorite folder.

        ExHentai does not provide a batch add endpoint, so galleries are processed
        individually (bounded by the shared semaphore). Returns list of failed gids.
        """
        if not items:
            return []
        if not (0 <= favcat <= 9):
            raise ValueError("favcat must be between 0 and 9")
        failed: list[int] = []
        finished: set[int] = set()
        try:
            for i, (gid, token) in enumerate(items):
                try:
                    await self.add_favorite(gid, token, favcat, note=note)
                    finished.add(gid)
                except EhClientError as exc:
                    logger.warning(
                        "add favorite failed on cloud",
                        extra=log_extra(gid=gid, favcat=favcat, error=str(exc)),
                    )
                    failed.append(gid)
                    finished.add(gid)
                    msg = str(exc).lower()
                    if "authentication" in msg or "expired" in msg:
                        failed.extend(g for g, _ in items[i + 1 :])
                        break
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "add favorite failed on cloud",
                        extra=log_extra(gid=gid, favcat=favcat, error=str(exc)),
                    )
                    failed.append(gid)
                    finished.add(gid)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "add favorites aborted",
                extra=log_extra(favcat=favcat, error=str(exc)),
            )
            failed.extend(
                items[idx][0]
                for idx in range(len(items))
                if items[idx][0] not in finished
            )
        return failed

    async def fetch_gmetadata(
        self, pairs: list[tuple[int, str]]
    ) -> dict[int, dict[str, Any]]:
        """Batch-fetch gallery metadata via the ExHentai ``gdata`` API.

        ExHentai caps each request at 25 galleries, so larger lists are chunked.
        Returns ``{gid: {thumb, title, title_jpn, category, file_count,
        file_size, tags}}`` for every gallery the API answered with.

        A chunk that fails is logged and skipped so the galleries already
        fetched are still returned; if no chunk succeeded the error is
        re-raised.  Quota/rate-limit errors abort immediately (retrying them
        would only deepen the limit).
        """
        result: dict[int, dict[str, Any]] = {}
        chunk_count = 0
        failed_chunks = 0
        last_error: EhClientError | None = None
        for start in range(0, len(pairs), EXHENTAI_API_CHUNK_SIZE):
            chunk_count += 1
            chunk = pairs[start : start + EXHENTAI_API_CHUNK_SIZE]
            payload = {
                "method": "gdata",
                "gidlist": [[int(gid), token] for gid, token in chunk],
                "namespace": 1,
            }
            try:
                response = await self._request(
                    "POST",
                    "/api.php",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Origin": self.settings.exhentai_base_url.rstrip("/"),
                    },
                )
                self._raise_for_status(response)
                try:
                    body = response.json()
                except ValueError as exc:
                    raise EhClientError("ExHentai gdata response was not JSON") from exc
            except EhQuotaExceededError:
                raise
            except EhClientError as exc:
                # A failed chunk must not discard the chunks that already
                # succeeded: keep the partial result and only fail hard when
                # nothing at all came back (single-chunk callers keep the old
                # "raise on failure" contract).
                failed_chunks += 1
                last_error = exc
                logger.warning(
                    "ExHentai gdata chunk failed",
                    extra=log_extra(gids=len(chunk), error=str(exc)),
                )
                continue
            for gallery in body.get("gmetadata", []) or []:
                if gallery.get("error") or gallery.get("gid") is None:
                    continue
                gid = int(gallery.get("gid"))
                parent = gallery.get("parent") or gallery.get("parent_gid") or ""
                parent_gid = int(parent) if str(parent).isdigit() else None
                result[gid] = {
                    "token": gallery.get("token") or "",
                    "thumb": html.unescape(gallery.get("thumb", "") or ""),
                    "title": html.unescape(gallery.get("title", "") or ""),
                    "title_jpn": (
                        html.unescape(gallery["title_jpn"])
                        if gallery.get("title_jpn")
                        else None
                    ),
                    "category": gallery.get("category") or None,
                    "file_count": int(gallery.get("filecount") or 0),
                    "file_size": int(gallery.get("filesize") or 0) or None,
                    "tags": gallery.get("tags", []) or [],
                    "posted": int(gallery.get("posted") or 0),
                    "expunged": bool(gallery.get("expunged")),
                    "uploader": gallery.get("uploader") or None,
                    "rating": float(gallery.get("rating") or 0) or None,
                    "parent_gid": parent_gid,
                }
        if failed_chunks and not result and last_error is not None:
            raise last_error
        if failed_chunks:
            logger.warning(
                "ExHentai gdata returned partial metadata",
                extra=log_extra(failed_chunks=failed_chunks, total_chunks=chunk_count),
            )
        return result

    async def fetch_gallery_by_category(self, category: str) -> tuple[int, str] | None:
        """Return the first ``(gid, token)`` listed for an ExHentai content category."""
        masks = {
            "doujinshi": 1,
            "manga": 2,
            "artistcg": 4,
            "gamecg": 8,
            "western": 16,
            "non-h": 32,
            "image_set": 64,
            "cosplay": 128,
            "asianporn": 256,
            "misc": 512,
        }
        mask = masks.get(category)
        if mask is None:
            return None
        response = await self._get("/", params={"f_cats": mask})
        match = re.search(r"/g/(\d+)/([0-9a-f]+)/", response.text)
        if not match:
            return None
        return int(match.group(1)), match.group(2)

    async def fetch_archive_info(self, gid: int, token: str) -> ArchiveInfo:
        """Read the archiver.php page: GP funds + original/resample costs/sizes.

        Read-only — nothing is charged here (charging happens on the POST in
        ``request_archive``).  Uses the shared page-fetch budget.
        """
        response = await self._get(
            f"/archiver.php?gid={int(gid)}&token={token}",
            headers={"Referer": f"/g/{int(gid)}/{token}/"},
        )
        return _parse_archive_info(response.text)

    async def fetch_gp_balance(self) -> int | None:
        """Read the current GP balance from the GP exchange page.

        archiver.php no longer shows ``You have X GP``, so the balance is
        taken from the exchange page's "Sell GP" box (``Available: N kGP``,
        displayed in thousands).  Returns None when the page is unreachable
        or the balance cannot be parsed.
        """
        try:
            response = await self._get("https://e-hentai.org/exchange.php?t=gp")
        except EhClientError:
            return None
        match = ARCHIVE_GP_BALANCE_RE.search(response.text)
        if not match:
            return None
        return int(float(match.group(1).replace(",", "")) * 1000)

    def _parse_image_limits(self, body: str) -> dict[str, int] | None:
        """Parse ``You are currently at X towards a limit of Y`` from a homepage body.

        Handles old/new markup with or without ``<strong>`` tags and plain text.
        Returns ``{"current": int, "limit": int}`` or None.
        """
        for pattern in (IMAGE_LIMIT_RE, IMAGE_LIMIT_SIMPLE_RE, IMAGE_LIMIT_PLAIN_RE):
            match = pattern.search(body)
            if match:
                try:
                    current = int(match.group(1).replace(",", ""))
                    limit = int(match.group(2).replace(",", ""))
                    return {"current": current, "limit": limit}
                except (ValueError, IndexError):
                    continue
        return None

    async def fetch_image_limits(self) -> dict[str, int] | None:
        """Read current / max image limits from the ExHentai homepage (home.php).

        The homepage box says "You are currently at X towards a limit of Y"
        (old) or "towards your account limit of Y" (new). Returns
        ``{"current": int, "limit": int}`` or None if unreachable, not logged
        in (Sad Panda), or the new IP-based quota hides the limit (post-2024).
        """
        for path in ("/home.php", "/"):
            try:
                response = await self._get(path)
            except EhClientError:
                continue
            body = response.text
            if _is_auth_failure_page(body) or _is_ip_banned_page(body):
                return None
            parsed = self._parse_image_limits(body)
            if parsed:
                return parsed
        return None

    async def request_archive(self, url: str, dltype: str) -> str:
        """Ask ExHentai to build the archive zip and return its download URL.

        ``dltype`` is ``org`` or ``res``.  This POST is what actually spends GP,
        so the executor persists the returned URL and never re-calls this for an
        already-requested archive.  Mirrors SXJ's ``downloadArchiver``: follow
        the ``document.location`` hop, then parse the zip link.
        """
        if dltype not in {"org", "res"}:
            raise ValueError("dltype must be 'org' or 'res'")
        dlcheck = (
            "Download Original Archive"
            if dltype == "org"
            else "Download Resample Archive"
        )
        origin = self.settings.exhentai_base_url.rstrip("/")
        response = await self._request(
            "POST",
            url,
            data={"dltype": dltype, "dlcheck": dlcheck},
            headers={"Referer": url, "Origin": origin},
        )
        self._raise_for_status(response)
        body = response.text
        direct = _parse_archiver_download_url(body)
        if direct:
            return urljoin(str(response.url), direct)
        location = ARCHIVER_LOCATION_RE.search(body)
        if not location:
            if _is_auth_failure_page(body) or _is_ip_banned_page(body):
                raise EhClientError("ExHentai authentication is required or expired")
            raise EhClientError("ExHentai archiver request returned no download link")
        continue_url = html.unescape(location.group(1))
        confirmation = await self._get(continue_url)
        link = _parse_archiver_download_url(confirmation.text)
        if not link:
            raise EhClientError("ExHentai archiver confirmation page has no download link")
        return urljoin(str(confirmation.url), link)

    async def download_archive(
        self, url: str, dest: Path, cb: Callable[[int, int | None], object] | None = None
    ) -> int:
        """Stream an archive zip to ``dest`` with Range resume support.

        Archives are served by ExHentai itself (not H@H nodes) and are long
        lived, so they take their own small budget (``_archive_semaphore``)
        instead of bypassing the limiters entirely, and the image chain's
        throughput watchdog (warm-up + minimum average speed) applies here too.
        There is deliberately no total wall-clock budget: a multi-GB archive can
        legitimately take many minutes, while a stalled or trickling transfer is
        still aborted.  ``cb(downloaded, total)`` receives byte progress.
        Returns the final total size.
        """
        host = (urlparse(url).hostname or "").lower()
        if not _is_allowed_eh_host(host, self.settings.exhentai_base_url):
            raise EhClientError(f"Disallowed host in archive URL: {host}")
        await self._archive_semaphore.acquire()
        self._stream_count += 1
        try:
            return await self._stream_archive(url, dest, cb)
        finally:
            self._stream_count -= 1
            self._archive_semaphore.release()

    async def _stream_archive(
        self, url: str, dest: Path, cb: Callable[[int, int | None], object] | None = None
    ) -> int:
        offset = dest.stat().st_size if dest.is_file() else 0
        headers = {"Referer": self.settings.exhentai_base_url.rstrip("/") + "/"}
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"
        timeout = httpx.Timeout(120.0, read=30.0)
        try:
            async with self.client.stream(
                "GET", url, headers=headers, timeout=timeout
            ) as response:
                if response.status_code in (401, 403) or "login" in str(
                    response.url
                ).lower():
                    raise EhClientError(
                        "ExHentai authentication is required or expired"
                    )
                if response.status_code in (429, 509):
                    raise EhClientError(
                        f"ExHentai rate limited (HTTP {response.status_code})"
                    )
                if response.status_code == 416:
                    total = _content_range_total(response.headers.get("content-range"))
                    if total is not None and offset == total:
                        return total
                    # Oversized or truncated partial: 416 with offset != total indicates
                    # corrupt/oversized local file. Clear so next attempt restarts cleanly.
                    if offset != 0:
                        logger.warning(
                            "archive download 416 range error, clearing corrupt partial file",
                            extra=log_extra(dest=str(dest), offset=offset, total=total),
                        )
                        dest.unlink(missing_ok=True)
                    raise EhClientError("ExHentai archive range is not satisfiable")
                if response.status_code == 200:
                    if offset > 0:
                        # Server ignored the Range header: restart from scratch.
                        dest.unlink(missing_ok=True)
                        offset = 0
                elif response.status_code != 206:
                    raise self._status_error(response)
                content_length = response.headers.get("content-length") or ""
                total = _content_range_total(
                    response.headers.get("content-range")
                ) or (offset + int(content_length) if content_length.isdigit() else None)
                downloaded = offset
                last_cb_time = 0.0
                last_cb_bytes = downloaded
                mode = "ab" if offset > 0 else "wb"
                started = time.monotonic()
                # Same watchdog as the image chain: the 30s read timeout only
                # fires when a transfer stalls completely, so a node trickling a
                # few KB/s could hold a worker (and its archive slot) forever.
                # No total budget here — archives are legitimately large.
                warmup = max(1, int(self.settings.image_slow_warmup_seconds))
                min_speed = max(1, int(self.settings.image_min_speed_kb_s)) * 1024
                with dest.open(mode) as handle:
                    async for chunk in response.aiter_bytes():
                        handle.write(chunk)
                        downloaded += len(chunk)
                        elapsed = time.monotonic() - started
                        if elapsed > warmup:
                            transferred = downloaded - offset
                            if transferred / elapsed < min_speed:
                                raise EhClientError(
                                    "ExHentai archive transfer throttled "
                                    f"({transferred / elapsed / 1024:.0f} KB/s < "
                                    f"{int(self.settings.image_min_speed_kb_s)} KB/s)"
                                )
                        if cb is not None:
                            now = time.monotonic()
                            if (
                                now - last_cb_time >= 0.2
                                or (total is not None and downloaded == total)
                                or (downloaded - last_cb_bytes >= 1024 * 1024)
                            ):
                                await cb(downloaded, total)
                                last_cb_time = now
                                last_cb_bytes = downloaded
                    if cb is not None and last_cb_bytes != downloaded:
                        await cb(downloaded, total)
            if total is not None and downloaded != total:
                raise EhClientError("ExHentai archive download was incomplete")
            return total if total is not None else downloaded
        except httpx.HTTPError as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (404, 410):
                raise ArchiveExpiredError("archive URL is expired or not found") from exc
            logger.warning(
                "archive download request failed",
                extra=log_extra(error=type(exc).__name__),
            )
            raise EhClientError("ExHentai archive download failed") from exc

    async def download_image(self, url: str) -> bytes:
        content, _ = await self.download_image_with_metadata(url)
        return content

    async def fetch_gallery_cover(self, gid: int | str, token: str | None = None) -> tuple[bytes, str]:
        """Download the gallery cover image, returning ``(bytes, content_type)``."""
        if token is None:
            gid, token = parse_gallery_url(str(gid), self.settings.exhentai_base_url)
        response = await self._get(f"/g/{int(gid)}/{token}/")
        match = re.search(
            r'id=["\']cover["\'][^>]*src=["\']([^"\']+)["\']', response.text, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'<div[^>]*id=["\']gd1["\'][^>]*>.*?'
                r'background[^:]*:\s*(?:transparent\s*)?url\(["\']?([^"\')]+)["\']?\)',
                response.text,
                re.IGNORECASE | re.DOTALL,
            )
        if not match:
            match = re.search(
                r'<div[^>]*id=["\']gd1["\'][^>]*>.*?<img[^>]+src=["\']([^"\']+)["\']',
                response.text,
                re.IGNORECASE | re.DOTALL,
            )
        if not match:
            raise GalleryGoneError("gallery has no cover")
        cover_url = urljoin(str(response.url), html.unescape(match.group(1)))
        # Route cover through the correct limiter (H@H images vs site pages),
        # mirroring download_image_with_metadata's host-based budget.
        host = (urlparse(cover_url).hostname or "").lower()
        if not _is_allowed_eh_host(host, self.settings.exhentai_base_url):
            raise EhClientError(f"Disallowed host in gallery cover URL: {host}")
        use_image_budget = "hath.network" in host or host.endswith(".ehgt.org")
        semaphore = self._image_semaphore if use_image_budget else self._semaphore
        t_wait_start = time.perf_counter()
        self._stream_count += 1
        try:
            async with semaphore:
                wait_elapsed = time.perf_counter() - t_wait_start
                observe_histogram(
                    "gv_ehclient_semaphore_wait_seconds",
                    wait_elapsed,
                    {"type": "image" if use_image_budget else "page"},
                )
                if isinstance(getattr(self.client, "event_hooks", None), dict):
                    resp_hooks = self.client.event_hooks.setdefault("response", [])
                    if self._check_redirect_host not in resp_hooks:
                        resp_hooks.append(self._check_redirect_host)
                cover_response = await self.client.get(
                    cover_url,
                    headers={"Referer": str(response.url)},
                    timeout=httpx.Timeout(120.0, read=30.0),
                    follow_redirects=True,
                )
        finally:
            self._stream_count -= 1
        for redirect_resp in getattr(cover_response, "history", []):
            loc = redirect_resp.headers.get("Location")
            if loc:
                redirect_url = urljoin(str(redirect_resp.url), loc)
                redirect_host = (urlparse(redirect_url).hostname or "").lower()
                if not _is_allowed_eh_host(redirect_host, self.settings.exhentai_base_url):
                    raise EhClientError(
                        f"Disallowed redirect host in gallery cover: {redirect_host}"
                    )
        final_host = (urlparse(str(cover_response.url)).hostname or "").lower()
        if not _is_allowed_eh_host(final_host, self.settings.exhentai_base_url):
            raise EhClientError(f"Disallowed host in gallery cover response: {final_host}")
        if cover_response.status_code in (401, 403) or "login" in str(cover_response.url).lower():
            raise EhClientError("ExHentai authentication is required or expired")
        self._raise_for_status(cover_response)
        if len(cover_response.content) < 200:
            # ExHentai answers galleries without a usable cover (or ones that
            # need a different H@H setup) with a 1x1 placeholder GIF.
            raise GalleryGoneError("gallery has no usable cover")
        return (
            cover_response.content,
            cover_response.headers.get("content-type", "image/jpeg").split(";")[0].strip(),
        )

    async def download_image_with_metadata(self, url: str) -> tuple[bytes, str]:
        host = (urlparse(url).hostname or "").lower()
        if not _is_allowed_eh_host(host, self.settings.exhentai_base_url):
            raise EhClientError(f"Disallowed host in image URL: {host}")
        # H@H image nodes (hath.network) are a distributed CDN with loose
        # limits — use the higher image limiter. Original-quality downloads
        # against the exhentai.org host stay on the page-fetch budget so we
        # don't trip anti-abuse on the site itself.
        use_image_budget = "hath.network" in host or host.endswith(".ehgt.org")
        semaphore = self._image_semaphore if use_image_budget else self._semaphore
        t_wait_start = time.perf_counter()
        self._stream_count += 1
        try:
            async with semaphore:
                wait_elapsed = time.perf_counter() - t_wait_start
                observe_histogram(
                    "gv_ehclient_semaphore_wait_seconds",
                    wait_elapsed,
                    {"type": "image" if use_image_budget else "page"},
                )
                # read=30s acts as a zero-progress watchdog (Ehviewer_CN_SXJ
                # aborts stalled downloads after ~3s of no bytes): a hanging H@H
                # node fails fast instead of holding the worker until the
                # overall timeout. 30s gives large images (GIF/animated) room
                # to resume after a node hiccup; the total budget below still
                # bounds the whole transfer.
                timeout = httpx.Timeout(120.0, read=30.0)
                # A throttled H@H node answers image requests with a tiny
                # "509" placeholder instead of the real file. Ehviewer_CN_SXJ
                # detects it by URL suffix; without the check the placeholder
                # would be saved as a legit page.
                if urlparse(url).path.rstrip("/").endswith(("/509.gif", "/509s.gif")):
                    raise EhImageSlowError("ExHentai rate limited (509 placeholder)")
                async with self.client.stream(
                    "GET",
                    url,
                    headers={"Referer": self.settings.exhentai_base_url.rstrip("/") + "/"},
                    timeout=timeout,
                ) as response:
                    if response.status_code in (429, 509):
                        raise EhClientError(
                            f"ExHentai rate limited (HTTP {response.status_code})"
                        )
                    if response.status_code in (401, 403):
                        raise EhClientError(
                            "ExHentai authentication is required or expired"
                        )
                    response.raise_for_status()
                    # Anti-hijack guard (Ehviewer_CN_SXJ mirrors this): if a
                    # redirect or a MITM sent us to a host outside ExHentai's own
                    # CDN/infra, the response is not the requested image.
                    final_host = (urlparse(str(response.url)).hostname or "").lower()
                    if (
                        final_host != host
                        and not final_host.endswith("hath.network")
                        and not final_host.endswith(".ehgt.org")
                        and final_host not in {"exhentai.org", "e-hentai.org"}
                    ):
                        raise EhClientError(
                            f"image download redirected to unexpected host: {final_host}"
                        )
                    chunks: list[bytes] = []
                    total = 0
                    started = time.monotonic()
                    # Watchdogs for a slow-but-alive H@H node: the 30s read
                    # timeout only fires when no bytes arrive at all, so a node
                    # trickling a few KB/s would otherwise hold the worker
                    # indefinitely.  Enforce a total wall-clock budget plus a
                    # minimum average throughput once past the warm-up window.
                    budget = max(1, int(self.settings.image_download_timeout_seconds))
                    warmup = max(1, int(self.settings.image_slow_warmup_seconds))
                    min_speed = max(1, int(self.settings.image_min_speed_kb_s)) * 1024
                    async for chunk in response.aiter_bytes():
                        chunks.append(chunk)
                        total += len(chunk)
                        elapsed = time.monotonic() - started
                        if elapsed > budget:
                            raise EhImageSlowError(
                                f"image download exceeded {budget}s budget "
                                f"({total / max(elapsed, 1e-6) / 1024:.0f} KB/s)"
                            )
                        if elapsed > warmup and total / elapsed < min_speed:
                            raise EhImageSlowError(
                                "H@H node throttled "
                                f"({total / elapsed / 1024:.0f} KB/s < "
                                f"{int(self.settings.image_min_speed_kb_s)} KB/s)"
                            )
                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";")[0]
                        .strip()
                    )
                    if not chunks or content_type.lower().startswith("text/"):
                        raise EhClientError("image response was not an image")
                    content_length = response.headers.get("content-length")
                    if (
                        content_length is not None
                        and content_length.isdigit()
                        and total != int(content_length)
                    ):
                        # Truncated by a proxy or a server hiccup — surface it as
                        # a retryable failure instead of writing a corrupt page.
                        raise EhClientError("image download was incomplete")
                    return b"".join(chunks), content_type
        except httpx.RequestError as exc:
            logger.warning(
                "image download request failed",
                extra=log_extra(error=type(exc).__name__, host=host),
            )
            raise EhClientError(
                f"ExHentai image download failed: {type(exc).__name__} on {host}"
            ) from exc
        finally:
            self._stream_count -= 1


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
