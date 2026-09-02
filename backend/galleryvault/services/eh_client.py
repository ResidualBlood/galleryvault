"""Small, testable ExHentai HTTP and HTML client."""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from ..config import Settings, get_settings
from ..logging import log_extra
from ..observability import observe_histogram

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

# ExHentai archive (archiver.php) page markers.  The page lists two POST forms
# (original / resample) that share the same action URL and differ only in the
# hidden ``dltype``; each carries its own ``Download Cost`` / ``Estimated Size``
# labels.  The GP balance appears near the top ("You have <b>…</b> GP").
ARCHIVE_COST_RE = re.compile(
    r"Download\s+Cost:?[^<]*<[^>]*>([^<]+)</[^>]+>", re.IGNORECASE
)
ARCHIVE_SIZE_RE = re.compile(
    r"Estimated\s+Size:?[^<]*<[^>]*>([^<]+)</[^>]+>", re.IGNORECASE
)
ARCHIVE_FUNDS_RE = re.compile(
    r"You have\s+(?:<[^>]*>\s*)*([0-9][0-9,.]*)\s*(?:<[^>]*>\s*)*GP", re.IGNORECASE
)
# The GP balance is no longer shown on archiver.php (ExHentai layout change);
# the authoritative balance lives on the GP exchange page ("Sell GP" box,
# ``Available: N kGP``).  A fallback that grabs any ``<number> GP`` would
# mis-read the ``Download Cost`` labels, so no per-page fallback regex.
ARCHIVE_GP_BALANCE_RE = re.compile(
    r"Available:\s*([0-9][0-9,.]*)\s*kGP", re.IGNORECASE
)
ARCHIVER_DOWNLOAD_LINK_RE = re.compile(
    r'href=["\']([^"\']+)["\']\s*>\s*Click Here To Start Downloading', re.IGNORECASE
)
ARCHIVER_LOCATION_RE = re.compile(r'document\.location\s*=\s*["\']([^"\']+)["\']')


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


class ArchiveExpiredError(EhClientError):
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


def parse_login_state(
    body: str, member_id: str = "", has_cookies: bool = False
) -> str:
    """Classify an ExHentai member-page response into a login state.

    ExHentai answers every session state with HTTP 200 and the public pages
    carry no login markers, so the member-only page body is the reliable
    signal (measured against production cookies):
    - a valid session returns the full page (tens of KB)
    - an expired/invalid session returns exactly ``expired login session``
    - a request without cookies returns an empty body (anti-bot challenge)
    - a Sad-Panda / IP-banned page has no content at all

    Returns one of ``ok`` / ``not_logged_in`` / ``no_exhentai_access`` /
    ``failed``.  An empty body is an anti-bot challenge or a transient glitch,
    not a dead session, so it is classified ``failed`` (a retry, not a cookie
    reset).  ``member_id`` / ``has_cookies`` are kept for signature
    compatibility but are no longer part of the classification.
    """
    if _is_auth_failure_page(body):
        return "no_exhentai_access"
    if not body:
        return "failed"
    if "expired login session" not in body:
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


@dataclass(frozen=True)
class ArchiveInfo:
    """Cost / size / form data parsed from an ExHentai archiver.php page.

    ``funds`` is the current GP balance (None when the page does not expose
    it).  Costs are in GP (0 for "Free!"), sizes in bytes.  The two forms share
    one action URL (``resample_url`` == ``original_url``) and differ only in
    the POST ``dltype`` value.
    """

    funds: int | None
    original_cost: int
    original_size: int
    original_url: str | None
    resample_cost: int
    resample_size: int
    resample_url: str | None


def _parse_archive_cost(text: str) -> int:
    """Parse a ``Download Cost`` value: "Free!" -> 0, a GP number otherwise."""
    if "free" in text.lower():
        return 0
    match = re.search(r"[0-9][0-9,.]*", text)
    if not match:
        return 0
    return int(float(match.group(0).replace(",", "")))


def _parse_archive_size(text: str) -> int:
    """Parse an ``Estimated Size`` label like ``18.46 MiB`` into bytes.

    Unparseable values (e.g. ``N/A`` when a tier is unavailable) yield 0.
    """
    number = re.search(r"[0-9]+(?:[.,][0-9]+)?", text)
    unit = re.search(r"(k|m|g|t)?(i?b)", text, re.IGNORECASE)
    if not number or not unit:
        return 0
    amount = float(number.group(0).replace(",", "."))
    multiplier = {
        "b": 1,
        "kb": 1024,
        "mb": 1024**2,
        "gb": 1024**3,
        "tb": 1024**4,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
    }.get((unit.group(1) or "").lower() + (unit.group(2) or "").lower(), 1)
    return int(amount * multiplier)


def _parse_archive_info(body: str) -> ArchiveInfo:
    """Parse an archiver.php page into ArchiveInfo (mirrors SXJ's parser).

    ``funds`` is parsed only from the explicit ``You have X GP`` balance row.
    The archiver page no longer renders it for every account/layout, so
    ``funds`` is often None here; callers should fall back to the GP exchange
    balance (``fetch_gp_balance``) when they need a real number.
    """
    funds: int | None = None
    funds_match = ARCHIVE_FUNDS_RE.search(body)
    if funds_match:
        funds = int(float(funds_match.group(1).replace(",", "")))
    costs: dict[str, int] = {"org": 0, "res": 0}
    sizes: dict[str, int] = {"org": 0, "res": 0}
    urls: dict[str, str | None] = {"org": None, "res": None}
    for form in re.finditer(
        r'<form\b[^>]*action=["\']([^"\']+)["\'][^>]*method=["\']post["\'][^>]*>(.*?)</form>',
        body,
        re.IGNORECASE | re.DOTALL,
    ):
        action, inner = form.group(1), form.group(2)
        dltype_match = re.search(
            r'<input[^>]*name=["\']dltype["\'][^>]*value=["\']([^"\']+)["\']',
            inner,
            re.IGNORECASE,
        )
        if not dltype_match:
            continue
        dltype = dltype_match.group(1).lower()
        if dltype not in {"org", "res"}:
            continue
        urls[dltype] = html.unescape(action)
        # Cost label sits just before the form, size just after it.
        before = body[max(0, form.start() - 260) : form.start()]
        after = body[form.end() : form.end() + 260]
        cost_match = ARCHIVE_COST_RE.search(before)
        size_match = ARCHIVE_SIZE_RE.search(after)
        if size_match and not re.search(r"[0-9]", size_match.group(1)):
            # ``N/A`` marks an unavailable tier (e.g. this gallery does not
            # qualify for a resample archive).  Clear its URL so callers treat
            # the tier as unavailable instead of charging/downloading blindly.
            urls[dltype] = None
        if cost_match:
            costs[dltype] = _parse_archive_cost(cost_match.group(1))
        if size_match:
            sizes[dltype] = _parse_archive_size(size_match.group(1))
    return ArchiveInfo(
        funds=funds,
        original_cost=costs["org"],
        original_size=sizes["org"],
        original_url=urls["org"],
        resample_cost=costs["res"],
        resample_size=sizes["res"],
        resample_url=urls["res"],
    )


def _parse_archiver_download_url(body: str) -> str | None:
    """The zip path behind the ``Click Here To Start Downloading`` link."""
    match = ARCHIVER_DOWNLOAD_LINK_RE.search(body)
    if not match:
        return None
    return html.unescape(match.group(1)).strip()


def _content_range_total(value: str | None) -> int | None:
    """``Content-Range`` total (``bytes 0-100/5000`` -> 5000)."""
    if not value:
        return None
    slash = value.rfind("/")
    if slash < 0 or slash == len(value) - 1:
        return None
    total = value[slash + 1 :].strip()
    if total.isdigit():
        return int(total)
    return None


def parse_gallery_url(value: str, base_url: str = "https://exhentai.org") -> tuple[int, str]:
    # Host validation to avoid SSRF via user-supplied evil.com/g/... URLs.
    # fetch_gallery builds its own URL from gid/token + base_url, but callers
    # that blindly use the parsed gid/token could be misled; reject non-ExHentai hosts early.
    try:
        parsed_input = urlparse(value)
        if parsed_input.scheme and parsed_input.hostname:
            host = parsed_input.hostname.lower()
            allowed = {"exhentai.org", "e-hentai.org"}
            if host not in allowed and not host.endswith((".exhentai.org", ".e-hentai.org")):
                raise ValueError("gallery URL must be on exhentai.org / e-hentai.org")
    except ValueError:
        raise
    except Exception:  # noqa: BLE001, S110
        pass
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

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owned:
            await self.client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        t_wait_start = time.perf_counter()
        async with self._semaphore:
            wait_elapsed = time.perf_counter() - t_wait_start
            observe_histogram("gv_ehclient_semaphore_wait_seconds", wait_elapsed, {"type": "page"})
            t_req_start = time.perf_counter()
            try:
                return await self.client.request(method, url, **kwargs)
            finally:
                req_elapsed = time.perf_counter() - t_req_start
                observe_histogram("gv_ehclient_request_duration_seconds", req_elapsed, {"method": method})

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
            status = exc.response.status_code
            logger.warning(
                "ExHentai returned HTTP error", extra=log_extra(status=status)
            )
            if status == 404:
                path = exc.request.url.path
                if path.startswith("/g/"):
                    raise GalleryGoneError("gallery does not exist on ExHentai (404)") from exc
                raise EhClientError(f"ExHentai request returned 404: {path}") from exc
            if status in (429, 509):
                raise EhClientError(f"ExHentai rate limited (HTTP {status})") from exc
            raise EhClientError("ExHentai returned an HTTP error") from exc

    async def check_login(self) -> tuple[str, str]:
        """Probe ExHentai and return ``(state, detail)``.

        ``state`` is one of ``ok`` / ``not_logged_in`` / ``no_exhentai_access`` /
        ``failed``; ``detail`` carries the HTTP status or exception type for the
        failure message. Probes ``/uconfig.php`` (a member-only settings page):
        every session state answers HTTP 200, but the body distinguishes them —
        a full page for a valid session, ``expired login session`` for a dead
        one, and an empty body when no cookies are sent. Retries once because
        ExHentai's occasional anti-bot challenge (an empty HTTP 200) is a
        transient glitch, not a login failure.
        """
        last_error: Exception | None = None
        for _ in range(2):
            try:
                response = await self._request("GET", "/uconfig.php")
            except httpx.RequestError as exc:
                last_error = exc
                continue
            if response.status_code in (401, 403) or "login" in str(response.url).lower():
                return "not_logged_in", f"HTTP {response.status_code}"
            return (
                parse_login_state(response.text),
                f"HTTP {response.status_code}",
            )
        return "failed", type(last_error).__name__

    async def fetch_gallery_metadata(self, gid: int, token: str) -> GalleryData:
        """Fetch only gallery metadata; tag sync must not enumerate or download pages."""
        response = await self._get(f"/g/{int(gid)}/{token}/")
        # Mirror fetch_gallery's anti-abuse challenge guard: ExHentai sometimes
        # 302s through remoteapi.php and lands on "/" with no content. The
        # cookie is still valid — treat as transient, not "gone".
        if not str(response.url.path).startswith("/g/"):
            raise EhClientError("ExHentai is challenging this client (temporary anti-abuse)")
        body = response.text
        if _is_auth_failure_page(body):
            raise EhClientError("ExHentai authentication is required or expired")
        if not body or not body.strip():
            raise EhClientError("ExHentai returned empty gallery page (temporary anti-abuse)")
        title, title_jpn = _parse_gallery_titles(body)
        tags = _parse_tags(body)
        if not title:
            # ExHentai answers non-existent / deleted galleries with a tiny
            # 200 page that has no title (or a real 404). But an empty/challenged
            # page also has no title — the guards above already filtered those, so
            # this remaining case is a genuine gone gallery.
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
            if response.status_code in (401, 403) or "login" in str(response.url).lower():
                raise EhClientError("ExHentai authentication is required or expired")
            response.raise_for_status()

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
            if response.status_code in (401, 403) or "login" in str(response.url).lower():
                raise EhClientError("ExHentai authentication is required or expired")
            response.raise_for_status()

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

    async def fetch_gmetadata(
        self, pairs: list[tuple[int, str]]
    ) -> dict[int, dict[str, Any]]:
        """Batch-fetch gallery metadata via the ExHentai ``gdata`` API.

        ExHentai caps each request at 25 galleries, so larger lists are chunked.
        Returns ``{gid: {thumb, title, title_jpn, category, file_count,
        file_size, tags}}`` for every gallery the API answered with.
        """
        result: dict[int, dict[str, Any]] = {}
        for start in range(0, len(pairs), EXHENTAI_API_CHUNK_SIZE):
            chunk = pairs[start : start + EXHENTAI_API_CHUNK_SIZE]
            payload = {
                "method": "gdata",
                "gidlist": [[int(gid), token] for gid, token in chunk],
                "namespace": 1,
            }
            response = await self._request(
                "POST",
                "/api.php",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Origin": self.settings.exhentai_base_url.rstrip("/"),
                },
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
        if response.status_code in (401, 403) or "login" in str(response.url).lower():
            raise EhClientError("ExHentai authentication is required or expired")
        response.raise_for_status()
        body = response.text
        direct = _parse_archiver_download_url(body)
        if direct:
            return urljoin(str(response.url), direct)
        location = ARCHIVER_LOCATION_RE.search(body)
        if not location:
            if _is_auth_failure_page(body):
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

        A single long-lived connection (no page semaphore): ExHentai serves the
        archive itself rather than through H@H nodes.  ``cb(downloaded, total)``
        receives byte progress.  Returns the final total size.
        """
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
                    response.raise_for_status()
                content_length = response.headers.get("content-length") or ""
                total = _content_range_total(
                    response.headers.get("content-range")
                ) or (offset + int(content_length) if content_length.isdigit() else None)
                downloaded = offset
                last_cb_time = 0.0
                last_cb_bytes = downloaded
                mode = "ab" if offset > 0 else "wb"
                with dest.open(mode) as handle:
                    async for chunk in response.aiter_bytes():
                        handle.write(chunk)
                        downloaded += len(chunk)
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
        use_image_budget = "hath.network" in host or host.endswith(".ehgt.org")
        semaphore = self._image_semaphore if use_image_budget else self._semaphore
        t_wait_start = time.perf_counter()
        async with semaphore:
            wait_elapsed = time.perf_counter() - t_wait_start
            observe_histogram(
                "gv_ehclient_semaphore_wait_seconds",
                wait_elapsed,
                {"type": "image" if use_image_budget else "page"},
            )
            cover_response = await self.client.get(
                cover_url,
                headers={"Referer": str(response.url)},
                timeout=httpx.Timeout(120.0, read=30.0),
                follow_redirects=True,
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
        t_wait_start = time.perf_counter()
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
