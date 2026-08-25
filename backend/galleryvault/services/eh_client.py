"""Small, testable ExHentai HTTP and HTML client."""

from __future__ import annotations

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
PAGE_RE = re.compile(r"/s/\d+/[A-Za-z0-9]+/(?P<page>[A-Za-z0-9]+)/")
IMAGE_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
TAG_ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bid=["\']ta_(?P<namespace>[^:"\']+):[^"\']+["\'][^>]*>(?P<name>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


class EhClientError(RuntimeError):
    pass


class GalleryGoneError(EhClientError):
    """The gallery no longer exists on ExHentai (HTTP 404).

    Local folders for deleted galleries will never sync successfully, so callers
    should treat this as terminal (skip) rather than a transient failure.
    """


class EhParseError(EhClientError):
    pass


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
    ) -> None:
        self.settings = settings or get_settings()
        self._owned = client is None
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

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self.client.get(url, **kwargs)
            if response.status_code in (401, 403) or "login" in str(response.url).lower():
                raise EhClientError("ExHentai authentication is required or expired")
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.ProxyError) as exc:
            logger.warning("ExHentai request failed", extra=log_extra(error=type(exc).__name__))
            raise EhClientError("ExHentai request failed") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning(
                "ExHentai returned HTTP error", extra=log_extra(status=status)
            )
            if status == 404:
                raise GalleryGoneError("gallery does not exist on ExHentai (404)") from exc
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
        body = response.text
        title, title_jpn = _parse_gallery_titles(body)
        # ExHentai lists roughly 20 page links per gallery page and paginates
        # long galleries with ?p=N.  Enumerate every gallery sub-page so whole
        # galleries are downloaded, not just the first screenful.
        page_hrefs: list[str] = []
        seen: set[str] = set()
        for offset in range(512):
            page_body = body if offset == 0 else None
            if page_body is None:
                page_response = await self._get(f"{base}?p={offset}")
                page_body = page_response.text
            collected = 0
            for href in re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', page_body, re.IGNORECASE):
                if re.search(r"/s/", href) and href not in seen:
                    seen.add(href)
                    page_hrefs.append(href)
                    collected += 1
            if max_pages is not None and max_pages > 0 and len(page_hrefs) >= max_pages:
                page_hrefs = page_hrefs[:max_pages]
                break
            if offset > 0 and collected == 0:
                break
        pages: list[GalleryPageData] = []
        for href in page_hrefs:
            absolute = urljoin(str(response.url), html.unescape(href))
            parsed = urlparse(absolute)
            page_token = PAGE_RE.search(parsed.path)
            page_token = (
                page_token.group("page")
                if page_token
                else parse_qs(parsed.query).get("p", [str(len(pages))])[0]
            )
            page_response = await self._get(absolute)
            image_match = None
            for image_tag in IMAGE_RE.finditer(page_response.text):
                tag = image_tag.group(0)
                if re.search(r'\bid=["\']img["\']', tag, re.IGNORECASE):
                    image_match = re.search(r'\bsrc=["\']([^"\']+)["\']', tag, re.IGNORECASE)
                    if image_match:
                        break
            if not image_match:
                raise EhClientError(f"viewer page has no image: {absolute}")
            image_url = urljoin(str(page_response.url), html.unescape(image_match.group(1)))
            origin_match = re.search(
                r'<a[^>]+href=["\']([^"\']+)fullimg([^"\']+)["\']', page_response.text, re.IGNORECASE
            )
            nl_match = re.search(
                r"nl\(\s*['\"]([^'\")]+)['\"]\s*\)", page_response.text
            )
            origin_url = (
                urljoin(str(page_response.url), html.unescape(origin_match.group(1)))
                + "fullimg"
                + html.unescape(origin_match.group(2))
                if origin_match
                else None
            )
            pages.append(
                GalleryPageData(
                    len(pages),
                    absolute,
                    page_token,
                    image_url,
                    origin_url,
                    nl_match.group(1) if nl_match else None,
                )
            )
        if not title or not pages:
            raise EhParseError("gallery HTML did not contain a title and page links")
        tags = _parse_tags(body)
        return GalleryData(
            int(gid), token, title, pages, tags, _parse_category(body), title_jpn
        )

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
                r'<a[^>]+href=["\']([^"\']*(?:/g/|/gallery/)[^"\']*)["\'][^>]*>(.*?)</a>',
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
                items.append(
                    FavoriteData(gid, token, _text(label), urljoin(str(response.url), href))
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

    async def download_image_with_metadata(self, url: str) -> tuple[bytes, str]:
        response = await self._get(url)
        if not response.content or response.headers.get("content-type", "").lower().startswith(
            "text/"
        ):
            raise EhClientError("image response was not an image")
        return response.content, response.headers.get("content-type", "")
