"""Small, testable ExHentai HTTP and HTML client."""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Self
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from ..config import Settings, get_settings
from ..logging import log_extra

logger = logging.getLogger(__name__)

# Ehviewer's Chrome User-Agent. ExHentai may throttle or block requests that do
# not look like a real browser, so we mirror Ehviewer rather than sending a
# custom agent that could get flagged.
EHVIEWER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
)

GALLERY_RE = re.compile(r"/(?:g|gallery)/(?P<gid>\d+)/(?P<token>[A-Za-z0-9]+)/")
# Legacy 3-segment viewer URL: /s/<gid>/<ptoken>/<page-token>/
PAGE_RE = re.compile(r"/s/\d+/[A-Za-z0-9]+/(?P<page>[A-Za-z0-9]+)/")
# Current ExHentai viewer URL: /s/<pToken>/<gid>-<page>  (mirrors Ehviewer_CN_SXJ's
# GalleryPageUrlParser). The 10-hex pToken is what Ehviewer stores in .ehviewer and
# sends as ``imgkey`` to the showpage API.
VIEWER_HREF_RE = re.compile(
    r"/s/(?P<ptoken>[0-9a-f]{10})/(?P<gid>\d+)-(?P<page>\d+)", re.IGNORECASE
)
IMAGE_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
TAG_ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bid=["\']ta_(?P<namespace>[^:"\']+):[^"\']+["\'][^>]*>(?P<name>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
# ExHentai /s/ viewer page embeds the API session key as ``var showkey="...";``.
SHOWKEY_RE = re.compile(r'var\s+showkey\s*=\s*"([0-9a-z]+)"', re.IGNORECASE)
# ``showpage`` API response fragments (i3 / i6 / i7) carry the resolved image HTML.
SHOWPAGE_IMAGE_RE = re.compile(r'<img[^>]*src="([^"]+)" style', re.IGNORECASE)
SHOWPAGE_SKIP_KEY_RE = re.compile(r"onclick=\"return nl\('([^\)]+)'\)")
SHOWPAGE_ORIGIN_PROMPT_RE = re.compile(
    r'<a href="#" onclick="prompt\(\'Copy the URL below\.\', \'([^\']+)\'\)'
)
SHOWPAGE_ORIGIN_RE = re.compile(r'<a href="([^"]+)fullimg([^"]+)">', re.IGNORECASE)


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


class EhClientError(RuntimeError):
    pass


class EhImageSlowError(EhClientError):
    """A single image download was aborted because its H@H node was too slow.

    Raised when a transfer never reaches a usable throughput (or exceeds the
    total wall-clock budget) but the connection stayed alive — a trickling node
    that would otherwise hold a download worker for many minutes.  Callers
    should back off and retry the page rather than re-hitting the node in a
    tight loop.
    """


class GalleryGoneError(EhClientError):
    """The gallery no longer exists on ExHentai (HTTP 404).

    Local folders for deleted galleries will never sync successfully, so callers
    should treat this as terminal (skip) rather than a transient failure.
    """


class EhParseError(EhClientError):
    pass


def _is_auth_failure_page(body: str) -> bool:
    """Detect the ExHentai sadpanda login / IP-banned page.

    These pages answer HTTP 200 with no gallery content, which callers would
    otherwise misread as "gallery deleted". Matching them here keeps auth
    expiry separate from genuine 404s so a dead session cannot mass-mark
    galleries as deleted.
    """
    return (
        "Sad Panda" in body
        or "Your IP address has been banned" in body
        or "Your IP address is temporarily banned" in body
    )


def parse_login_state(body: str, member_id: str = "") -> str:
    """Classify an ExHentai home-page response into a login state.

    Returns one of:
    - ``ok``: the page carries an authenticated session
    - ``not_logged_in``: the page is served (HTTP 200) but shows no login state
    - ``no_exhentai_access``: a Sad-Panda / IP-banned page with no content

    ``_is_auth_failure_page`` covers the Sad-Panda / banned pages; the rest is
    the normal homepage where a logged-out session still answers 200 (the case
    a plain reachability check would wrongly report as "ok").
    """
    if _is_auth_failure_page(body):
        return "no_exhentai_access"
    # Logged-in pages carry the My Home link; the configured member id is the
    # strongest signal that this specific account is authenticated.
    if "home.php" in body or "My Home" in body:
        return "ok"
    if member_id and member_id in body:
        return "ok"
    return "not_logged_in"


@dataclass(frozen=True)
class GalleryPageData:
    index: int
    url: str
    token: str
    image_url: str | None = None
    origin_url: str | None = None
    skip_hath_key: str | None = None


class ShowkeyState:
    """Mutable holder for the ExHentai ``showkey`` shared by page resolutions.

    The showkey is per-gallery (seeded from the first viewer HTML and refreshed
    by later ones) and must outlive any single ``fetch_gallery`` call so the
    lazy per-page URL resolution in the downloader keeps working without
    re-fetching the gallery metadata.
    """

    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value: str | None = None


@dataclass(frozen=True)
class GalleryData:
    gid: int
    token: str
    title: str
    pages: list[GalleryPageData]
    tags: list[dict[str, str]] = field(default_factory=list)
    category: str = "other"
    title_jpn: str | None = None
    file_size: int | None = None


@dataclass(frozen=True)
class FavoriteData:
    gid: int
    token: str
    title: str
    url: str
    thumb: str | None = None


def parse_gallery_url(value: str, base_url: str = "https://exhentai.org") -> tuple[int, str]:
    match = GALLERY_RE.search(value)
    if not match:
        compact = re.fullmatch(r"\s*(\d+)\s*/\s*([0-9a-fA-F]+)\s*", value)
        if compact:
            return int(compact.group(1)), compact.group(2)
    if not match:
        query = parse_qs(urlparse(value).query)
        if query.get("gid") and query.get("t"):
            return int(query["gid"][0]), query["t"][0]
        raise ValueError("expected an ExHentai gallery URL or gid/token")
    return int(match["gid"]), match["token"]


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _parse_gallery_titles(body: str) -> tuple[str, str | None]:
    """Return (display_title, japanese_title) from a gallery detail page.

    ExHentai exposes the romaji/English title in ``#gn`` and the Japanese title
    in ``#gj``. Ehviewer defaults to showing the Japanese title.
    """
    gn = re.search(r'id=["\']gn["\'][^>]*>(.*?)</h1>', body, re.IGNORECASE | re.DOTALL)
    gj = re.search(r'id=["\']gj["\'][^>]*>(.*?)</h1>', body, re.IGNORECASE | re.DOTALL)
    title = _text(gn.group(1)) if gn else ""
    if not title:
        fallback_title = re.search(
            r"<h1[^>]*class=[\"']gm[\"'][^>]*>(.*?)</h1>|<h1[^>]*>(.*?)</h1>|<title>(.*?)</title>",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        if fallback_title:
            title = _text(next(part for part in fallback_title.groups() if part))
    title_jpn = _text(gj.group(1)) if gj else None
    return title, title_jpn


def _parse_tags(body: str) -> list[dict[str, str]]:
    """Parse current ExHentai tag link ids with a fallback for older markup."""
    tags = [
        {"namespace": match.group("namespace"), "name": _text(match.group("name"))}
        for match in TAG_ANCHOR_RE.finditer(body)
    ]
    if not tags:
        tags = [
            {"namespace": match.group(1), "name": _text(match.group(2))}
            for match in re.finditer(
                r'<div[^>]*class=["\'][^"\']*gt[^"\']*["\'][^>]*>(.*?)</div>',
                body,
                re.IGNORECASE | re.DOTALL,
            )
            for match in [re.search(r"^\s*([^:]+):\s*(.*)$", _text(match.group(1)))]
            if match
        ]
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for tag in tags:
        key = (tag["namespace"], tag["name"])
        if tag["name"] and key not in seen:
            seen.add(key)
            unique.append(tag)
    return unique


def _favorites_next_url(body: str) -> str:
    """The ``next`` cursor URL embedded by ExHentai for favorites paging."""
    match = re.search(r"var\s+nexturl\s*=\s*\"([^\"]*)\"", body)
    if not match:
        return ""
    value = match.group(1).strip()
    if not value or "next=" not in value:
        return ""
    return value


def _parse_file_size(body: str) -> int | None:
    """Total archive size in bytes from the gallery info table (``32.63 MiB``)."""
    match = re.search(
        r"File\s*Size:.*?<td[^>]*>([0-9.,]+\s*(?:[KMGT]?i?B|bytes?))</td>",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    value = match.group(1).strip()
    number = re.sub(r"[^0-9.]", "", value)
    try:
        amount = float(number)
    except ValueError:
        return None
    unit = re.sub(r"[0-9.,\s]", "", value).lower()
    multipliers = {
        "b": 1,
        "kb": 1024,
        "kib": 1024,
        "mb": 1024**2,
        "mib": 1024**2,
        "gb": 1024**3,
        "gib": 1024**3,
    }
    return int(amount * multipliers.get(unit, 1))


def _parse_category(body: str) -> str:
    from ..scanners.base import normalize_category

    match = re.search(
        r'<div[^>]+class=["\']cs ct\d["\'][^>]*>(.*?)</div>', body, re.IGNORECASE | re.DOTALL
    )
    if not match:
        match = re.search(
            r"(?:category|gdc)[^>]{0,200}>(.*?)<", body, re.IGNORECASE | re.DOTALL
        )
    return normalize_category(_text(match.group(1)) if match else "other")


def _parse_favorite_counts(body: str) -> dict[int, int]:
    """Per-folder gallery counts from the favorites page header (fp blocks).

    ExHentai renders each favorite folder's current size in the page header
    (``<div class="fp">…<div>234</div> <div>1 长篇大作</div>…``), so a single
    request yields every folder's count without paging through the galleries.
    """
    result: dict[int, int] = {}
    for block in re.finditer(
        r'<div[^>]+class=["\']fp["\'][\s\S]*?</div>\s*</div>', body, re.IGNORECASE
    ):
        category = re.search(r"favcat=(\d+)", block.group(0), re.IGNORECASE)
        parts = _text(block.group(0)).split(maxsplit=2)
        if category and len(parts) >= 2 and parts[0].isdigit():
            result[int(category.group(1))] = int(parts[0])
    return result


def _parse_favorite_categories(body: str) -> dict[int, str]:
    result: dict[int, str] = {}
    patterns = (
        r'<option[^>]+value=["\'](?P<id>[0-9])["\'][^>]*>(?P<name>.*?)</option>',
        r'<a[^>]+(?:href|data-favcat)=["\'][^"\']*(?:favcat=|favcat/)(?P<id>[0-9])[^"\']*["\'][^>]*>(?P<name>.*?)</a>',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, body, re.IGNORECASE | re.DOTALL):
            name = _text(match.group("name"))
            if name:
                result[int(match.group("id"))] = name
    for block in re.finditer(
        r'<div[^>]+class=["\']fp["\'][\s\S]*?</div>\s*</div>', body, re.IGNORECASE
    ):
        category = re.search(r"favcat=(\d+)", block.group(0), re.IGNORECASE)
        parts = _text(block.group(0)).split(maxsplit=2)
        if category and len(parts) >= 2:
            name = parts[2] if len(parts) == 3 and parts[1].isdigit() else " ".join(parts[1:])
            if name:
                result[int(category.group(1))] = name
    return {index: result[index] for index in sorted(result)}


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
        # of parallel requests and trip ExHentai's anti-abuse.
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        # Image downloads go to the H@H network (hath.network) which is a
        # distributed CDN with its own generous limits — mirroring Ehviewer's
        # 32-thread IO pool, we give images their own, higher limiter instead of
        # sharing the page-fetch budget.
        self._image_semaphore = asyncio.Semaphore(max(8, max(1, max_concurrency) * 2))
        if client is not None:
            self.client = client
        else:
            proxy = self.settings.socks5_proxy or self.settings.http_proxy
            cookies = dict(self.settings.exhentai_cookies)
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
                headers={"User-Agent": EHVIEWER_USER_AGENT},
                follow_redirects=True,
            )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owned:
            await self.client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async with self._semaphore:
            return await self.client.request(method, url, **kwargs)

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._request("GET", url, **kwargs)
            if (
                response.status_code in (401, 403)
                or "login" in str(response.url).lower()
                or _is_auth_failure_page(response.text)
            ):
                raise EhClientError("ExHentai authentication is required or expired")
            response.raise_for_status()
            # Buffer the body inside the try so a connection reset while reading
            # is wrapped as EhClientError below instead of leaking a raw
            # RemoteProtocolError to the download worker.
            response.read()
            return response
        except httpx.RequestError as exc:
            # Covers TimeoutException, ConnectError, ReadError,
            # RemoteProtocolError, ProxyError — every transient transport
            # failure must surface as EhClientError so callers retry instead of
            # treating a dead proxy/DNS blip as a permanent per-gallery failure.
            logger.warning("ExHentai request failed", extra=log_extra(error=type(exc).__name__))
            raise EhClientError("ExHentai request failed") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning(
                "ExHentai returned HTTP error", extra=log_extra(status=status)
            )
            if status == 404:
                raise GalleryGoneError("gallery does not exist on ExHentai (404)") from exc
            if status in (429, 509):
                raise EhClientError(f"ExHentai rate limited (HTTP {status})") from exc
            raise EhClientError("ExHentai returned an HTTP error") from exc

    async def check_login(self) -> tuple[str, str]:
        """Probe ExHentai and return ``(state, detail)``.

        ``state`` is one of ``ok`` / ``not_logged_in`` / ``no_exhentai_access`` /
        ``failed``; ``detail`` carries the HTTP status or exception type for the
        failure message. Retries once because ExHentai's occasional anti-bot
        challenge (a 302 through remoteapi.php) is a transient glitch, not a
        login failure.
        """
        member_id = str((self.settings.exhentai_cookies or {}).get("ipb_member_id", ""))
        last_error: Exception | None = None
        for _ in range(2):
            try:
                response = await self._request("GET", "/")
            except httpx.RequestError as exc:
                last_error = exc
                continue
            if response.status_code in (401, 403) or "login" in str(response.url).lower():
                return "not_logged_in", f"HTTP {response.status_code}"
            return (
                parse_login_state(response.text, member_id),
                f"HTTP {response.status_code}",
            )
        return "failed", type(last_error).__name__

    async def fetch_gallery_metadata(self, gid: int, token: str) -> GalleryData:
        """Fetch only gallery metadata; tag sync must not enumerate or download pages."""
        response = await self._get(f"/g/{int(gid)}/{token}/")
        body = response.text
        title, title_jpn = _parse_gallery_titles(body)
        tags = _parse_tags(body)
        if not title:
            # ExHentai answers non-existent / deleted galleries with a tiny
            # 200 page that has no title (or a real 404). Treat both as gone.
            raise GalleryGoneError("gallery does not exist on ExHentai")
        return GalleryData(
            int(gid), token, title, [], tags, _parse_category(body), title_jpn,
            _parse_file_size(body),
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
            raise EhClientError("ExHentai is challenging this client (temporary anti-abuse)")
        body = response.text
        title, title_jpn = _parse_gallery_titles(body)
        # ExHentai lists roughly 20 page links per gallery page and paginates
        # long galleries with ?p=N.  Enumerate every gallery sub-page so whole
        # galleries are downloaded, not just the first screenful.
        page_hrefs: list[str] = []
        seen: set[str] = set()

        def _collect_hrefs(page_body: str, limit: int | None = None) -> int:
            """Collect viewer hrefs from one gallery page; returns count added."""
            collected = 0
            for href in re.findall(
                r'<a[^>]+href=["\']([^"\']+)["\']', page_body, re.IGNORECASE
            ):
                if re.search(r"/s/", href) and href not in seen:
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
                return offset, page_response.text

            fetched: dict[int, str] = {}
            try:
                for offset, text in await asyncio.gather(
                    *(_fetch_page(o) for o in offsets)
                ):
                    fetched[offset] = text
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
            for offset in range(start, 512):
                page_response = await self._get(f"{base}?p={offset}")
                if _collect_hrefs(page_response.text, max_pages) == 0:
                    break
                if max_pages is not None and max_pages > 0 and len(page_hrefs) >= max_pages:
                    break
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
            nl_match = re.search(r"nl\(\s*['\"]([^'\")]+)['\"]\s*\)", body)
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
                nl_match.group(1) if nl_match else None,
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
                info = await self._showpage(gid, page, p_token, showkey.value)
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
        self, gid: int, page: GalleryPageData, showkey: ShowkeyState | None = None
    ) -> GalleryPageData:
        """Resolve one page's fresh image URLs right before downloading.

        Called by the downloader per page so the keystamp is never stale (a
        long gallery would otherwise serve URLs signed 20 minutes earlier,
        which H@H nodes reject with 403).  Prefers the lightweight showpage
        API when a showkey is known and falls back to full HTML otherwise.
        """
        if showkey is None:
            showkey = ShowkeyState()
        absolute = page.url
        viewer = VIEWER_HREF_RE.search(absolute)
        p_token = viewer.group("ptoken") if viewer else (page.token or "")
        page_num = int(viewer.group("page")) if viewer else page.index + 1
        if showkey.value:
            try:
                info = await self._showpage(gid, page_num, p_token, showkey.value)
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
        nl_match = re.search(r"nl\(\s*['\"]([^'\")]+)['\"]\s*\)", body)
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
            nl_match.group(1) if nl_match else None,
        )

    async def _showpage(
        self, gid: int, page: int, p_token: str, showkey: str
    ) -> dict[str, str]:
        """Resolve one page's image URLs via the ExHentai ``showpage`` API.

        ``page`` is 1-based.  Returns ``{image_url, origin_url, skip_hath_key}``
        exactly like parsing the viewer HTML would, but from a small JSON body.
        """
        payload = {
            "method": "showpage",
            "gid": int(gid),
            "page": int(page),
            "imgkey": p_token,
            "showkey": showkey,
        }
        try:
            response = await self._request(
                "POST",
                "/api.php",
                json=payload,
                headers={"Content-Type": "application/json"},
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
        if response.status_code in (401, 403) or "login" in str(response.url).lower():
            raise EhClientError("ExHentai authentication is required or expired")
        response.raise_for_status()
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
                origin_url = (
                    html.unescape(origin_match.group(1))
                    + "fullimg"
                    + html.unescape(origin_match.group(2))
                )
        if origin_url is None:
            prompt_match = SHOWPAGE_ORIGIN_PROMPT_RE.search(i6)
            if prompt_match:
                origin_url = html.unescape(prompt_match.group(1))
        return {
            "image_url": image_url,
            "origin_url": origin_url,
            "skip_hath_key": skip_hath_key,
        }

    async def fetch_favorites(
        self,
        favcat: int,
        progress: Callable[[int], object] | None = None,
    ) -> list[FavoriteData]:
        """Fetch every gallery in a favorite folder, following ExHentai paging.

        ExHentai favorites are paginated with a ``next`` cursor embedded in the
        page (``var nexturl="...?favcat=N&next=gid-timestamp"``) rather than a
        ``page`` number; walking only the first page silently drops the tail of
        a large folder.  ``progress`` (if given) is called with the number of
        galleries collected so far after every page.
        """
        result: list[FavoriteData] = []
        seen: set[int] = set()
        url = "/favorites.php"
        params: dict[str, object] = {"favcat": int(favcat)}
        while True:
            response = await self._get(url, params=params)
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
                items.append(
                    FavoriteData(
                        gid,
                        token,
                        title,
                        urljoin(str(response.url), href),
                        thumbs.get(gid),
                    )
                )
            if not items:
                break
            result.extend(items)
            if progress is not None:
                progress(len(result))
            next_url = html.unescape(_favorites_next_url(response.text))
            if not next_url:
                break
            parsed = urlparse(next_url)
            url = parsed.path or "/favorites.php"
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        return result

    async def fetch_favorite_categories(self) -> dict[int, str]:
        response = await self._get("/favorites.php")
        return _parse_favorite_categories(response.text)

    async def fetch_favorite_counts(self) -> dict[int, int]:
        """Current per-folder gallery counts from one favorites.php request."""
        response = await self._get("/favorites.php")
        return _parse_favorite_counts(response.text)

    async def remove_favorites(self, gids: list[int]) -> None:
        """Remove galleries from ExHentai favorites (across all folders).

        Mirrors Ehviewer_CN_SXJ: POST /favorites.php with ``ddact=delete`` and
        one ``modifygids[]`` entry per gid.  A non-2xx response is raised so the
        caller can surface a cloud sync failure.
        """
        if not gids:
            return
        form = {"ddact": "delete", "apply": "Apply", "modifygids[]": [str(int(g)) for g in gids]}
        response = await self._request(
            "POST",
            "/favorites.php",
            data=form,
            headers={"Referer": urljoin(str(self.client.base_url), "/favorites.php")},
        )
        if response.status_code in (401, 403) or "login" in str(response.url).lower():
            raise EhClientError("ExHentai authentication is required or expired")
        response.raise_for_status()

    async def fetch_gmetadata(
        self, pairs: list[tuple[int, str]]
    ) -> dict[int, dict[str, Any]]:
        """Batch-fetch gallery metadata via the ExHentai ``gdata`` API.

        ExHentai caps each request at 25 galleries, so larger lists are chunked.
        Returns ``{gid: {thumb, title, title_jpn, category, file_count,
        file_size, tags}}`` for every gallery the API answered with.
        """
        result: dict[int, dict[str, Any]] = {}
        for start in range(0, len(pairs), 25):
            chunk = pairs[start : start + 25]
            payload = {
                "method": "gdata",
                "gidlist": [[int(gid), token] for gid, token in chunk],
                "namespace": 1,
            }
            response = await self._request(
                "POST",
                "/api.php",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code in (401, 403) or "login" in str(response.url).lower():
                raise EhClientError("ExHentai authentication is required or expired")
            response.raise_for_status()
            try:
                body = response.json()
            except ValueError as exc:
                raise EhClientError("ExHentai gdata response was not JSON") from exc
            for gallery in body.get("gmetadata", []) or []:
                gid = int(gallery.get("gid"))
                result[gid] = {
                    "token": gallery.get("token") or "",
                    "thumb": html.unescape(gallery.get("thumb", "") or ""),
                    "title": gallery.get("title", "") or "",
                    "title_jpn": gallery.get("title_jpn") or None,
                    "category": gallery.get("category") or None,
                    "file_count": int(gallery.get("filecount") or 0),
                    "file_size": int(gallery.get("filesize") or 0) or None,
                    "tags": gallery.get("tags", []) or [],
                    "posted": int(gallery.get("posted") or 0),
                    "expunged": bool(gallery.get("expunged")),
                    "uploader": gallery.get("uploader") or None,
                    "rating": float(gallery.get("rating") or 0) or None,
                }
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
        cover_response = await self._request(
            "GET",
            cover_url,
            headers={"Referer": str(response.url)},
        )
        if cover_response.status_code in (401, 403) or "login" in str(cover_response.url).lower():
            raise EhClientError("ExHentai authentication is required or expired")
        cover_response.raise_for_status()
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
        # H@H image nodes (hath.network) are a distributed CDN with loose
        # limits — use the higher image limiter. Original-quality downloads
        # against the exhentai.org host stay on the page-fetch budget so we
        # don't trip anti-abuse on the site itself.
        use_image_budget = "hath.network" in host or host.endswith(".ehgt.org")
        semaphore = self._image_semaphore if use_image_budget else self._semaphore
        try:
            async with semaphore:
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
                    # Watchdogs for a slow-but-alive H@H node: the 15s read
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
                extra=log_extra(error=type(exc).__name__),
            )
            raise EhClientError("ExHentai image download failed") from exc
