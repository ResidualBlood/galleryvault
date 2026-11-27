"""Search / listing data classes, cursors and listing-page HTML parsing."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, urljoin, urlparse

from .errors import _is_auth_failure_page, _is_ip_banned_page
from .favorites import _favorites_next_url
from .gallery import _text, parse_gallery_url

__all__ = [
    'JUMP_VALUES',
    '_LIST_CLASS_RE',
    '_LIST_POSTED_RE',
    '_LIST_TAG_NODE_RE',
    '_LIST_TITLE_RE',
    '_LIST_UPLOADER_RE',
    '_NEXT_CURSOR_RE',
    '_TOPLIST_CURSOR_RE',
    'EhSearchResult',
    'SearchGallery',
    '_cursor_from_url',
    '_cursor_param',
    '_search_category',
    '_search_item_window',
    '_search_next_cursor',
    '_search_pages',
    '_search_posted',
    '_search_rating',
    '_search_tags',
    '_search_thumb',
    '_search_uploader',
    '_thumb_from_img_attrs',
    '_thumbs_from_listing_cells',
    '_toplist_next_cursor',
    '_usable_thumb_src',
    'classify_search_body',
    'get_fixed_preview_thumb_url',
    'normalize_jump',
    'normalize_seek',
    'parse_search_page',
    'parse_search_prev_cursor',
]


@dataclass(frozen=True)
class SearchGallery:
    gid: int
    token: str
    title: str
    url: str
    thumb: str | None = None
    category: str | None = None
    pages: int | None = None
    rating: float | None = None
    # List-row tags parsed from the ``.gt``/``.gtl`` ``title`` attributes.
    # Empty when the account uses a list mode without tags (thumbnail/minimal).
    tags: list[dict[str, str]] = field(default_factory=list)
    posted: int | None = None
    uploader: str | None = None


@dataclass
class EhSearchResult:
    items: list[SearchGallery]
    next_cursor: str | None = None
    state: str = "ok"
    prev_cursor: str | None = None


_NEXT_CURSOR_RE = re.compile(r"^\d+(-\d+)?$")
_TOPLIST_CURSOR_RE = re.compile(r"^\d+$")

# Date-jump values accepted by E-Hentai / ExHentai list pages.
# Reference: EhViewer_CN_SXJ `JumpDateSelector.nodePickerAppendBuild`
# (`jump=1d|3d|1w|2w|1m|6m|1y|2y`).  ``seek`` always uses ``YYYY-MM-DD``.
JUMP_VALUES = frozenset({"1d", "3d", "1w", "2w", "1m", "6m", "1y", "2y"})


def normalize_jump(value: str | None) -> str | None:
    """Validate an ExHentai ``jump`` interval (e.g. ``1m``)."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw not in JUMP_VALUES:
        raise ValueError("invalid jump")
    return raw


def normalize_seek(value: str | None) -> str | None:
    """Validate an ExHentai ``seek`` date (``YYYY-MM-DD``)."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC).date()
    except ValueError as exc:
        raise ValueError("invalid seek date") from exc
    if parsed.isoformat() != raw:
        raise ValueError("invalid seek date")
    return raw


def _toplist_next_cursor(body: str, cur_p: int) -> str | None:
    """Detect next page cursor for E-Hentai toplist (uses p=N query parameter)."""
    next_p = cur_p + 1
    if next_p < 200 and re.search(rf"(?:[?&]|&amp;)p={next_p}\b", body):
        return str(next_p)
    return None


def _cursor_from_url(value: str) -> str | None:
    if not value:
        return None
    qs = parse_qs(urlparse(html.unescape(value)).query)
    cur = (qs.get("next") or [""])[0].strip()
    if _NEXT_CURSOR_RE.fullmatch(cur):
        return cur
    return None


def _search_next_cursor(body: str) -> str | None:
    """ExHentai list paging cursor (``next=gid-ts``), same source as favorites."""
    cur = _cursor_from_url(_favorites_next_url(body))
    if cur:
        return cur
    unext = re.search(
        r'<a[^>]+id=["\']unext["\'][^>]*href=["\']([^"\']+)["\']',
        body,
        re.IGNORECASE,
    )
    if not unext:
        unext = re.search(
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*id=["\']unext["\']',
            body,
            re.IGNORECASE,
        )
    if unext:
        cur = _cursor_from_url(unext.group(1))
        if cur:
            return cur
    fallback = re.search(r"[?&]next=(\d+(?:-\d+)?)", body)
    if fallback:
        return fallback.group(1)
    return None


def _cursor_param(url: str, param: str) -> str | None:
    qs = parse_qs(urlparse(html.unescape(url)).query)
    cur = (qs.get(param) or [""])[0].strip()
    if _NEXT_CURSOR_RE.fullmatch(cur):
        return cur
    return None


def parse_search_prev_cursor(body: str) -> str | None:
    """ExHentai list ``prev`` cursor from the ``#uprev`` nav link.

    The listing emits ``<a id="uprev" href="...&prev=gid-ts">``; the first page
    has no such link, so ``None`` means "no previous page".
    """
    for pattern in (
        r'<a[^>]+id=["\']uprev["\'][^>]*href=["\']([^"\']+)["\']',
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*id=["\']uprev["\']',
    ):
        match = re.search(pattern, body, re.IGNORECASE)
        if not match:
            continue
        cur = _cursor_param(match.group(1), "prev")
        if cur:
            return cur
    return None


def _search_item_window(body: str, gid: int, token: str) -> str:
    needle = f"/g/{gid}/{token}"
    idx = body.find(needle)
    if idx < 0:
        idx = body.find(f"/g/{gid}/")
    if idx < 0:
        return ""
    start = body.rfind("<tr", 0, idx)
    if start < 0:
        gl1t = body.rfind('class="gl1t"', 0, idx)
        if gl1t >= 0:
            start = body.rfind("<div", 0, gl1t + 1)
    if start < 0:
        start = max(0, idx - 1500)
        for match in re.finditer(r"/g/(\d+)/", body[start:idx]):
            if int(match.group(1)) != gid:
                start = start + match.end()
    end = body.find("</tr>", idx)
    if end < 0 or end > idx + 4000:
        end = idx + 800
        nxt = re.search(rf"/g/(?!{gid}\b)\d+/", body[idx + 10 : idx + 2000])
        if nxt:
            end = idx + 10 + nxt.start()
    else:
        end += 5
    return body[start:end]


def get_fixed_preview_thumb_url(origin: str) -> str:
    src = origin.strip()
    if src.startswith("//"):
        src = "https:" + src
    parsed = urlparse(src)
    if not parsed.scheme or not parsed.netloc:
        return src
    segments = [part for part in parsed.path.split("/") if part]
    if len(segments) < 3:
        return src
    last, second, third = segments[-1], segments[-2], segments[-3]
    if last.startswith(third) and last.startswith(second, len(third)):
        return f"https://ehgt.org/{third}/{second}/{last}"
    host = parsed.netloc.lower()
    eh_host = (
        host == "ehgt.org"
        or host.endswith(".ehgt.org")
        or host in {"s.exhentai.org", "exhentai.org", "e-hentai.org"}
    )
    if eh_host and segments[0].lower() == "w":
        return "https://ehgt.org/" + "/".join(segments)
    return src


def _usable_thumb_src(url: str | None) -> str | None:
    if not url:
        return None
    src = html.unescape(url).strip()
    low = src.lower()
    if not src or src.startswith("data:"):
        return None
    if any(skip in low for skip in ("/509.gif", "/509s.gif", "blank.gif")):
        return None
    fixed = get_fixed_preview_thumb_url(src)
    parsed = urlparse(fixed)
    if parsed.netloc.lower() != "ehgt.org":
        return None
    if re.fullmatch(r"/g/[a-z0-9]+\.(png|gif|jpg|webp|svg)", parsed.path.lower()):
        return None
    if parsed.scheme.lower() != "https":
        return f"https://ehgt.org{parsed.path}"
    return fixed


def _thumb_from_img_attrs(attrs: str) -> str | None:
    data_src = re.search(r"\bdata-src=[\"']([^\"']+)[\"']", attrs, re.IGNORECASE)
    src = re.search(r"(?<![\w-])src=[\"']([^\"']+)[\"']", attrs, re.IGNORECASE)
    picked = _usable_thumb_src(data_src.group(1) if data_src else None)
    if picked:
        return picked
    return _usable_thumb_src(src.group(1) if src else None)


def _search_thumb(snippet: str) -> str | None:
    for match in re.finditer(r"<img([^>]+)>", snippet, re.IGNORECASE):
        picked = _thumb_from_img_attrs(match.group(1))
        if picked:
            return picked
    return None


def _thumbs_from_listing_cells(body: str, base_url: str) -> dict[int, str]:
    thumbs: dict[int, str] = {}
    for match in re.finditer(
        r"<(?:div|td)\b([^>]*class=[\"'][^\"']*\b(?:glthumb|gl1e|gl3t)\b[^\"']*[\"'][^>]*)>",
        body,
        re.IGNORECASE,
    ):
        snippet = body[match.end() : match.end() + 2500]
        thumb = _search_thumb(snippet)
        if not thumb:
            continue
        gid: int | None = None
        id_m = re.search(r'\bid=["\']it(\d+)["\']', match.group(1), re.IGNORECASE)
        if id_m:
            gid = int(id_m.group(1))
        else:
            href_m = re.search(
                r'href=["\']([^"\']*(?:/g/|/gallery/)[^"\']*)["\']',
                snippet,
                re.IGNORECASE,
            )
            if href_m:
                try:
                    gid, _ = parse_gallery_url(href_m.group(1), base_url)
                except ValueError:
                    gid = None
            if gid is None:
                nearby = re.search(r"/g/(\d+)/", body[match.start() : match.start() + 4000])
                if nearby:
                    gid = int(nearby.group(1))
        if gid is not None and gid not in thumbs:
            thumbs[gid] = thumb
    return thumbs


def _search_pages(snippet: str) -> int | None:
    match = re.search(r"(\d+)\s*pages?", snippet, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _search_rating(snippet: str) -> float | None:
    match = re.search(r"Average:\s*([0-9]+(?:\.[0-9]+)?)", snippet, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _search_category(snippet: str) -> str | None:
    match = re.search(
        r'<div[^>]+class=["\']c[sn][^"\']*["\'][^>]*>(.*?)</div>',
        snippet,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.search(
            r'<td[^>]+class=["\'][^"\']*glcat[^"\']*["\'][^>]*>(.*?)</td>',
            snippet,
            re.IGNORECASE | re.DOTALL,
        )
    if not match:
        return None
    from ....scanners.base import normalize_category

    return normalize_category(_text(match.group(1)))


# List rows render tags as ``<div class="gt" title="female:sole female">f:sole female</div>``.
# The ``title`` attribute keeps the full ``namespace:name`` pair while the text is
# abbreviated, so only the attribute is reliable for a machine-readable tag.
_LIST_TAG_NODE_RE = re.compile(r"<(?:div|span)\b([^>]*)>", re.IGNORECASE)
_LIST_CLASS_RE = re.compile(r'class=["\']([^"\']*)["\']', re.IGNORECASE)
_LIST_TITLE_RE = re.compile(r'title=["\']([^"\']*)["\']', re.IGNORECASE)
# Compact/extended list rows expose the post time in a hidden ``posted_<gid>``
# node; thumbnail/minimal modes omit it, in which case ``posted`` is None.
_LIST_POSTED_RE = re.compile(r'id=["\']posted_\d+["\'][^>]*>\s*([^<]+?)\s*<', re.IGNORECASE)
_LIST_UPLOADER_RE = re.compile(
    r'href=["\'][^"\']*/uploader/[^"\']*["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)


def _search_tags(snippet: str) -> list[dict[str, str]]:
    """Tags from a list-row window, read from ``.gt``/``.gtl`` ``title`` attrs.

    The abbreviated text (``f:sole female``) is deliberately ignored: the
    attribute carries the full namespace. A value without ``:`` is kept as a
    ``misc`` tag. Order is preserved and duplicates are dropped.
    """
    tags: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for node in _LIST_TAG_NODE_RE.finditer(snippet):
        attrs = node.group(1)
        classes = _LIST_CLASS_RE.search(attrs)
        if not classes or not ({"gt", "gtl"} & set(classes.group(1).split())):
            continue
        title = _LIST_TITLE_RE.search(attrs)
        if not title:
            continue
        value = html.unescape(title.group(1)).strip()
        if not value:
            continue
        namespace, name = value.split(":", 1) if ":" in value else ("misc", value)
        namespace = namespace.strip() or "misc"
        name = name.strip()
        if not name:
            continue
        key = (namespace, name)
        if key in seen:
            continue
        seen.add(key)
        tags.append({"namespace": namespace, "name": name})
    return tags


def _search_posted(snippet: str) -> int | None:
    """UTC timestamp from the row's ``posted_<gid>`` text (None when absent)."""
    match = _LIST_POSTED_RE.search(snippet)
    if not match:
        return None
    parts = re.fullmatch(
        r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})",
        _text(match.group(1)).strip(),
    )
    if not parts:
        return None
    try:
        parsed = datetime(*(int(part) for part in parts.groups()), tzinfo=UTC)
    except ValueError:
        return None
    return int(parsed.timestamp())


def _search_uploader(snippet: str) -> str | None:
    match = _LIST_UPLOADER_RE.search(snippet)
    if not match:
        return None
    name = _text(match.group(1)).strip()
    return name or None


def parse_search_page(
    body: str, base_url: str = "https://exhentai.org"
) -> tuple[list[SearchGallery], str | None]:
    """Parse an ExHentai gallery listing (search / front page) into rows + cursor.

    Title / thumb / ``next=`` extraction matches ``fetch_favorites`` (same
    ``parse_gallery_url`` + ``glink`` + ``var nexturl`` style). Category, page
    count and rating are read from a window around each gallery URL.
    """
    thumbs = _thumbs_from_listing_cells(body, base_url)
    for tm in re.finditer(
        r'<a[^>]+href=["\']([^"\']*(?:/g/|/gallery/)[^"\']*)["\'][^>]*>'
        r"\s*<img([^>]+)>",
        body,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            tgid, _ = parse_gallery_url(tm.group(1), base_url)
        except ValueError:
            continue
        if tgid in thumbs:
            continue
        thumb = _thumb_from_img_attrs(tm.group(2))
        if thumb:
            thumbs[tgid] = thumb
    items: list[SearchGallery] = []
    seen: set[int] = set()
    for href, label in re.findall(
        r'<a[^>]+href=["\']([^"\']*(?:/g/|/gallery/)[^"\']*)["\'][^>]*>(?![^<]*<img)(.*?)</a>',
        body,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            gid, token = parse_gallery_url(href, base_url)
        except ValueError:
            continue
        if gid in seen:
            continue
        seen.add(gid)
        glink = re.search(
            r'<div[^>]*class=["\']glink["\'][^>]*>(.*?)</div>',
            label,
            re.IGNORECASE | re.DOTALL,
        )
        title = _text(glink.group(1)) if glink else _text(label)
        snippet = _search_item_window(body, gid, token)
        items.append(
            SearchGallery(
                gid,
                token,
                title,
                urljoin(base_url.rstrip("/") + "/", href),
                thumbs.get(gid) or _search_thumb(snippet),
                _search_category(snippet),
                _search_pages(snippet),
                _search_rating(snippet),
                _search_tags(snippet),
                _search_posted(snippet),
                _search_uploader(snippet),
            )
        )
    return items, _search_next_cursor(body)


def classify_search_body(body: str) -> str:
    if _is_ip_banned_page(body):
        return "ip_banned"
    if _is_auth_failure_page(body):
        return "no_exhentai_access"
    if not body or not str(body).strip():
        return "challenge"
    if "expired login session" in body:
        return "not_logged_in"
    return "ok"