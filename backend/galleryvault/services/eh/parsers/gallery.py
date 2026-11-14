"""Gallery data classes and gallery detail / listing-preview HTML parsing."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from .showpage import _parse_file_size

__all__ = [
    'GALLERY_RE',
    'IMAGE_RE',
    'TAG_ANCHOR_RE',
    '_AVERAGE_RATING_RE',
    '_COVER_RE',
    '_LENGTH_RE',
    '_NEWER_HINT',
    '_PARENT_RE',
    '_POSTED_RE',
    '_PREVIEW_ANCHOR_RE',
    '_SPRITE_HEIGHT_RE',
    '_SPRITE_POS_RE',
    '_SPRITE_STYLE_RE',
    '_SPRITE_URL_RE',
    '_SPRITE_WIDTH_RE',
    '_UPLOADER_RE',
    'GalleryData',
    'GalleryPageData',
    'OnlineGalleryDetail',
    'PageThumb',
    'PreviewItem',
    'PreviewPage',
    '_parse_category',
    '_parse_gallery_titles',
    '_parse_pages',
    '_parse_parent_gid',
    '_parse_posted',
    '_parse_tags',
    '_sprite_thumb',
    '_tags_from_gdata',
    '_text',
    'parse_gallery_preview',
    'parse_gallery_url',
    'parse_newer_gallery',
    'parse_online_gallery',
]


GALLERY_RE = re.compile(r"/(?:g|gallery)/(?P<gid>\d+)/(?P<token>[A-Za-z0-9]+)/?")
# Legacy 3-segment viewer URL: /s/<gid>/<ptoken>/<page-token>/


IMAGE_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
TAG_ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bid=["\']ta_(?P<namespace>[^:"\']+):[^"\']+["\'][^>]*>(?P<name>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
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
    replaced_by: tuple[int, str] | None = None


@dataclass(frozen=True)
class OnlineGalleryDetail:
    """Everything the online detail page needs, from one gallery HTML fetch.

    ``gdata`` only fills fields the HTML page does not expose reliably (or as
    typed values), so the dataclass is transport-agnostic and testable from a
    saved page.
    """

    gid: int
    token: str
    title: str
    title_jpn: str | None = None
    category: str = "other"
    uploader: str | None = None
    posted: int | None = None
    pages: int | None = None
    rating: float | None = None
    file_size: int | None = None
    thumb: str | None = None
    tags: list[dict[str, str]] = field(default_factory=list)
    newer: tuple[int, str] | None = None
    parent_gid: int | None = None


@dataclass(frozen=True)
class PageThumb:
    """One gallery page thumbnail cut out of the H@H sprite sheet."""

    index: int
    url: str
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class PreviewItem:
    """One viewer page on a preview page; ``thumb`` is None when unparsable."""

    index: int
    thumb: PageThumb | None


@dataclass(frozen=True)
class PreviewPage:
    """One ExHentai gallery ``?p=`` preview page.

    ``ptokens`` maps page index → viewer token.  It must stay server-side: the
    public pages response only exposes ``index`` and the sprite ``thumb``.
    ``items`` keeps an entry (with ``thumb=None``) for every viewer link, so a
    sprite/markup change degrades to a placeholder instead of a missing page.
    """

    total: int | None
    items: list[PreviewItem]
    ptokens: dict[int, str]


def parse_gallery_url(value: str, base_url: str = "https://exhentai.org") -> tuple[int, str]:
    # Host validation to avoid SSRF via user-supplied evil.com/g/... URLs.
    # fetch_gallery builds its own URL from gid/token + base_url, but callers
    # that blindly use the parsed gid/token could be misled; reject non-ExHentai hosts early.
    raw = value.strip()
    host = (urlparse(raw).hostname or "").lower()
    if not host and not raw.startswith(("/", "?", "#")):
        # Schemeless absolute form ("evil.com/g/1/abc/"): urlparse() puts the
        # whole string in ``path`` and reports no host, so the check above would
        # be skipped. Re-parse with an authority marker and validate a
        # host-looking first segment (a plain "123/abcdef" gid/token pair is
        # kept valid).
        candidate = urlparse("//" + raw)
        candidate_host = (candidate.hostname or "").lower()
        if "." in candidate_host or ":" in candidate_host:
            host = candidate_host
    if host:
        allowed = {"exhentai.org", "e-hentai.org"}
        if host not in allowed and not host.endswith((".exhentai.org", ".e-hentai.org")):
            raise ValueError("gallery URL must be on exhentai.org / e-hentai.org")
    match = GALLERY_RE.search(value)
    if not match:
        compact = re.fullmatch(r"\s*/*\s*(\d+)\s*/\s*([0-9a-fA-F]+)\s*/*\s*", value)
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


_NEWER_HINT = re.compile(
    r"replaced with a newer version|newer version of (?:this |the )?gallery|"
    r"a newer version is available|listing is no longer available|"
    r"新しいバージョン",
    re.IGNORECASE,
)


def parse_newer_gallery(body: str, current_gid: int) -> tuple[int, str] | None:
    """Return ``(gid, token)`` of a replacement gallery advertised on the page.

    ExHentai shows a banner plus a ``/g/<gid>/<token>/`` link when a listing has
    been replaced. Parent (older) links are ignored by requiring the hint text
    and skipping ``current_gid``. Only the hint block and the nearest gallery
    URL after the hint are considered.
    """
    if not body:
        return None
    hint = _NEWER_HINT.search(body)
    if not hint:
        return None
    rest = body[hint.start() :]
    for match in GALLERY_RE.finditer(rest):
        gid = int(match["gid"])
        if gid != int(current_gid):
            return gid, match["token"]
    return None


_PREVIEW_ANCHOR_RE = re.compile(
    r'<a\b[^>]*href="(?P<href>[^"]*?/s/(?P<ptoken>[0-9a-fA-F]+)/'
    r'(?P<gid>\d+)-(?P<index>\d+))"[^>]*>(?P<inner>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SPRITE_STYLE_RE = re.compile(r'style="([^"]*)"', re.IGNORECASE)
_SPRITE_URL_RE = re.compile(r"url\(\s*['\"]?(?P<url>[^)'\"]+)['\"]?\s*\)", re.IGNORECASE)
_SPRITE_POS_RE = re.compile(
    r"url\([^)]*\)\s*(?P<x>-?\d+)(?:px)?\s+(?P<y>-?\d+)(?:px)?", re.IGNORECASE
)
_SPRITE_WIDTH_RE = re.compile(r"width:\s*(\d+)px", re.IGNORECASE)
_SPRITE_HEIGHT_RE = re.compile(r"height:\s*(\d+)px", re.IGNORECASE)
_LENGTH_RE = re.compile(
    r"Length:.*?<td[^>]*>\s*([0-9,]+)\s*pages?", re.IGNORECASE | re.DOTALL
)
_UPLOADER_RE = re.compile(
    r'id=["\']gdn["\'][^>]*>.*?<a[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)
_POSTED_RE = re.compile(
    r"Posted:\s*</td>\s*<td[^>]*>\s*([^<]+?)\s*</td>", re.IGNORECASE | re.DOTALL
)
_PARENT_RE = re.compile(
    r"Parent:\s*</td>\s*<td[^>]*>\s*([^<]+?)\s*</td>", re.IGNORECASE | re.DOTALL
)
_AVERAGE_RATING_RE = re.compile(r"Average:\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_COVER_RE = re.compile(
    r'id=["\']gd1["\'][^>]*>.*?url\((?P<url>[^)]+)\)', re.IGNORECASE | re.DOTALL
)


def _parse_pages(body: str) -> int | None:
    """Gallery image count from the info table's ``Length: N pages`` row."""
    match = _LENGTH_RE.search(body or "")
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_posted(body: str) -> int | None:
    """Unix timestamp from the detail page's ``Posted:`` row.

    ExHentai renders the time in the account's configured timezone, so the
    value is only a fallback; ``gdata``'s ``posted`` is authoritative.
    """
    match = _POSTED_RE.search(body or "")
    if not match:
        return None
    parts = re.fullmatch(
        r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})",
        match.group(1).strip(),
    )
    if not parts:
        return None
    try:
        parsed = datetime(*(int(part) for part in parts.groups()), tzinfo=UTC)
    except ValueError:
        return None
    return int(parsed.timestamp())


def _parse_parent_gid(body: str) -> int | None:
    match = _PARENT_RE.search(body or "")
    if not match:
        return None
    value = match.group(1).strip()
    return int(value) if value.isdigit() else None


def _tags_from_gdata(raw: object) -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw or []:  # type: ignore[union-attr]
        namespace = ""
        name = ""
        if isinstance(item, dict):
            namespace = str(item.get("namespace") or "")
            name = str(item.get("name") or "")
        else:
            text = str(item or "")
            if ":" in text:
                namespace, name = text.split(":", 1)
            else:
                name = text
        namespace = namespace.strip()
        name = name.strip()
        if not name or (namespace, name) in seen:
            continue
        seen.add((namespace, name))
        tags.append({"namespace": namespace, "name": name})
    return tags


def _sprite_thumb(inner: str, index: int) -> PageThumb | None:
    """Cut one sprite cell out of an anchor's inner markup (None on drift)."""
    style_match = _SPRITE_STYLE_RE.search(inner or "")
    if not style_match:
        return None
    style = style_match.group(1)
    url_match = _SPRITE_URL_RE.search(style)
    pos_match = _SPRITE_POS_RE.search(style)
    width_match = _SPRITE_WIDTH_RE.search(style)
    height_match = _SPRITE_HEIGHT_RE.search(style)
    if not (url_match and pos_match and width_match and height_match):
        return None
    return PageThumb(
        index=index,
        url=html.unescape(url_match.group("url")),
        x=int(pos_match.group("x")),
        y=int(pos_match.group("y")),
        w=int(width_match.group(1)),
        h=int(height_match.group(1)),
    )


def parse_gallery_preview(body: str, gid: int) -> PreviewPage:
    """Parse one gallery preview page: total, page indices and sprite thumbs.

    Viewer links are the page index source (``/s/<ptoken>/<gid>-<n>``); each
    link's sprite cell is parsed independently so a markup change only nulls
    that page's thumbnail.  ``ptokens`` never leaves the server boundary.
    """
    items: dict[int, PreviewItem] = {}
    ptokens: dict[int, str] = {}
    for match in _PREVIEW_ANCHOR_RE.finditer(body or ""):
        try:
            link_gid = int(match.group("gid"))
            index = int(match.group("index"))
        except (TypeError, ValueError):
            continue
        if link_gid != int(gid) or index <= 0 or index in items:
            continue
        ptokens[index] = match.group("ptoken")
        items[index] = PreviewItem(index=index, thumb=_sprite_thumb(match.group("inner"), index))
    total = _parse_pages(body)
    if total is None and items:
        total = max(items)
    return PreviewPage(
        total=total,
        items=[items[index] for index in sorted(items)],
        ptokens=ptokens,
    )


def parse_online_gallery(
    body: str,
    gid: int,
    token: str,
    *,
    gdata: dict[str, object] | None = None,
) -> OnlineGalleryDetail:
    """Compose the online detail payload from gallery HTML (+ optional gdata).

    The detail HTML is the required source (title/tags/category/newer/thumb and
    every table row); ``gdata`` supersedes only fields where it has typed or
    more reliable values (posted epoch, rating, file count, uploader, parent).
    """
    data = gdata or {}
    title, title_jpn = _parse_gallery_titles(body)
    gdata_title = data.get("title")
    if gdata_title:
        title = str(gdata_title)
    gdata_title_jpn = data.get("title_jpn")
    if gdata_title_jpn:
        title_jpn = str(gdata_title_jpn)
    if title_jpn is not None and not str(title_jpn).strip():
        title_jpn = None
    tags = _parse_tags(body)
    if not tags:
        tags = _tags_from_gdata(data.get("tags"))
    category = _parse_category(body)
    gdata_category = data.get("category")
    if gdata_category:
        category = str(gdata_category)
    uploader_match = _UPLOADER_RE.search(body or "")
    uploader = _text(uploader_match.group(1)) if uploader_match else None
    if data.get("uploader"):
        uploader = str(data.get("uploader"))
    posted_value = data.get("posted")
    posted = int(posted_value) if posted_value else None
    if posted is None:
        posted = _parse_posted(body)
    rating_value = data.get("rating")
    rating = float(rating_value) if rating_value else None
    if rating is None:
        rating_match = _AVERAGE_RATING_RE.search(body or "")
        rating = float(rating_match.group(1)) if rating_match else None
    pages_value = data.get("file_count")
    pages = int(pages_value) if pages_value else None
    if pages is None:
        pages = _parse_pages(body)
    file_size_value = data.get("file_size")
    file_size = int(file_size_value) if file_size_value else None
    if file_size is None:
        file_size = _parse_file_size(body)
    thumb = str(data.get("thumb") or "") or None
    if not thumb:
        cover_match = _COVER_RE.search(body or "")
        thumb = html.unescape(cover_match.group("url").strip()) if cover_match else None
    parent_value = data.get("parent_gid")
    parent_gid = int(parent_value) if parent_value else None
    if parent_gid is None:
        parent_gid = _parse_parent_gid(body)
    return OnlineGalleryDetail(
        gid=int(gid),
        token=token,
        title=title,
        title_jpn=title_jpn,
        category=category,
        uploader=uploader,
        posted=posted,
        pages=pages,
        rating=rating,
        file_size=file_size,
        thumb=thumb,
        tags=tags,
        newer=parse_newer_gallery(body, int(gid)),
        parent_gid=parent_gid,
    )


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


def _parse_category(body: str) -> str:
    from ....scanners.base import normalize_category

    match = re.search(
        r'<div[^>]+class=["\']cs ct\d["\'][^>]*>(.*?)</div>', body, re.IGNORECASE | re.DOTALL
    )
    if not match:
        match = re.search(
            r"(?:category|gdc)[^>]{0,200}>(.*?)<", body, re.IGNORECASE | re.DOTALL
        )
    return normalize_category(_text(match.group(1)) if match else "other")