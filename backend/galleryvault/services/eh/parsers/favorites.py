"""Favorites data classes and favorites-page HTML parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .gallery import _text

__all__ = [
    'FavoriteData',
    'FavoriteItems',
    '_favorites_next_url',
    '_parse_favorite_categories',
    '_parse_favorite_counts',
    'parse_favorite_note',
]


@dataclass(frozen=True)
class FavoriteData:
    gid: int
    token: str
    title: str
    url: str
    thumb: str | None = None
    note: str | None = None


class FavoriteItems(list[FavoriteData]):
    """A favorite-folder listing carrying how far its cloud page can be trusted.

    An empty list alone is ambiguous: the folder may really be empty, or the
    page markup may have changed and no gallery link matched. ``confirmed_empty``
    is only True when a valid favorites page reported a cloud count of zero for
    the folder; ``truncated`` marks a listing that stopped short of the count in
    the page header (pagination silently ended). Callers must not delete local
    records on an empty list unless ``confirmed_empty`` is set.
    """

    def __init__(self, items: list[FavoriteData] | None = None) -> None:
        super().__init__(items or [])
        self.confirmed_empty = False
        self.truncated = False
        self.cloud_count: int | None = None


def _favorites_next_url(body: str) -> str:
    """The ``next`` cursor URL embedded by ExHentai for favorites paging."""
    # ExHentai emits either quote style; matching only ``"`` silently stopped
    # after page 1 if the markup changed, truncating favorites.
    match = re.search(r"var\s+nexturl\s*=\s*[\"']([^\"']*)[\"']", body)
    if not match:
        return ""
    value = match.group(1).strip()
    if not value or "next=" not in value:
        return ""
    return value


def parse_favorite_note(snippet: str, gid: int) -> str | None:
    """Extract a per-gallery favorite note from listing HTML when present."""
    patterns = (
        rf'id=["\']favnote{int(gid)}["\'][^>]*>(.*?)</(?:div|p|td)>',
        r'<div[^>]*class=["\'][^"\']*glnote[^"\']*["\'][^>]*>(.*?)</div>',
        r'<p[^>]*class=["\'][^"\']*(?:glnote|note)[^"\']*["\'][^>]*>(.*?)</p>',
    )
    for pattern in patterns:
        match = re.search(pattern, snippet, re.IGNORECASE | re.DOTALL)
        if match:
            text = _text(match.group(1)).strip()
            if text:
                return text
    return None


def _parse_favorite_counts(body: str) -> dict[int, int] | None:
    """Per-folder gallery counts from the favorites page header (fp blocks).

    ExHentai renders each favorite folder's current size in the page header
    (``<div class="fp">…<div>234</div> <div>1 长篇大作</div>…``), so a single
    request yields every folder's count without paging through the galleries.

    Returns ``None`` when no folder header could be parsed (wrong page, login
    wall, or markup drift) so callers can tell "could not confirm" apart from a
    parsed header that reports zero items (``{0: 0}``).
    """
    result: dict[int, int] = {}
    for block in re.finditer(
        r'<div[^>]+class=["\']fp["\'][\s\S]*?</div>\s*</div>', body, re.IGNORECASE
    ):
        category = re.search(r"favcat=(\d+)", block.group(0), re.IGNORECASE)
        parts = _text(block.group(0)).split(maxsplit=2)
        if category and len(parts) >= 2 and parts[0].isdigit():
            result[int(category.group(1))] = int(parts[0])
    return result or None


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