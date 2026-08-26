"""Small, testable ExHentai HTTP and HTML client."""

from __future__ import annotations

import asyncio
import html
import logging
import re
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


class EhClientError(RuntimeError):
    pass


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


@dataclass(frozen=True)
class GalleryPageData:
    index: int
    url: str
    token: str
    image_url: str | None = None
    origin_url: str | None = None
    skip_hath_key: str | None = None


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
        self, gid: int | str, token: str | None = None, max_pages: int | None = None
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
        if gallery_pages > 1:
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
        for offset in range(start, 512):
            page_response = await self._get(f"{base}?p={offset}")
            if _collect_hrefs(page_response.text, max_pages) == 0:
                break
            if max_pages is not None and max_pages > 0 and len(page_hrefs) >= max_pages:
                break
        pages: list[GalleryPageData] = []
        showkey: str | None = None

        async def _resolve_page_html(href: str) -> GalleryPageData:
            """Resolve one viewer page from its full HTML (also yields the showkey).

            Falling back to the HTML path (instead of the showpage API) keeps the
            client working when the API rejects or the gallery page format differs.
            """
            nonlocal showkey
            absolute = urljoin(str(response.url), html.unescape(href))
            viewer = VIEWER_HREF_RE.search(absolute)
            p_token = viewer.group("ptoken") if viewer else None
            if p_token is None:
                parsed = urlparse(absolute)
                legacy = PAGE_RE.search(parsed.path)
                p_token = (
                    legacy.group("page")
                    if legacy
                    else parse_qs(parsed.query).get("p", [""])[0]
                )
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
            if showkey_match and not showkey:
                showkey = showkey_match.group(1)
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
            absolute = urljoin(str(response.url), html.unescape(href))
            viewer = VIEWER_HREF_RE.search(absolute)
            if not viewer:
                return await _resolve_page_html(href)
            p_token = viewer.group("ptoken")
            page = int(viewer.group("page"))
            if not showkey:
                return await _resolve_page_html(href)
            try:
                info = await self._showpage(int(gid), page, p_token, showkey)
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

        # Resolve every viewer page concurrently (bounded by the shared ExHentai
        # semaphore): serial resolution of a 255-page gallery took minutes.  The
        # first page is resolved via HTML first so its ``showkey`` is available
        # for the lightweight showpage API on the remaining pages.
        if page_hrefs:
            first = await _resolve_page_html(page_hrefs[0])
            pages = [first]
            if len(page_hrefs) > 1:
                pages.extend(
                    await asyncio.gather(
                        *(_resolve_page_api(h) for h in page_hrefs[1:])
                    )
                )
        pages = [
            GalleryPageData(
                index, r.url, r.token, r.image_url, r.origin_url, r.skip_hath_key
            )
            for index, r in enumerate(pages)
        ]
        if not title or not pages:
            raise EhParseError("gallery HTML did not contain a title and page links")
        tags = _parse_tags(body)
        return GalleryData(
            int(gid), token, title, pages, tags, _parse_category(body), title_jpn
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
                items.append(FavoriteData(gid, token, title, urljoin(str(response.url), href)))
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
                # read=15s acts as a zero-progress watchdog (Ehviewer_CN_SXJ
                # aborts stalled downloads after ~3s of no bytes): a hanging H@H
                # node fails fast instead of holding the worker until the 60s
                # overall timeout.
                timeout = httpx.Timeout(60.0, read=15.0)
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
                    async for chunk in response.aiter_bytes():
                        chunks.append(chunk)
                        total += len(chunk)
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
                "image download request failed", extra={"error": type(exc).__name__}
            )
            raise EhClientError("ExHentai image download failed") from exc
