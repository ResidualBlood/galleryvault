"""SHOWKEY / showpage viewer markers, showkey state and byte-size helpers."""

from __future__ import annotations

import re

# Legacy 3-segment viewer URL: /s/<gid>/<ptoken>/<page-token>/
__all__ = [
    'PAGE_RE',
    'SHOWKEY_RE',
    'SHOWPAGE_IMAGE_RE',
    'SHOWPAGE_ORIGIN_PROMPT_RE',
    'SHOWPAGE_ORIGIN_RE',
    'SHOWPAGE_SKIP_KEY_RE',
    'VIEWER_HREF_RE',
    'ShowkeyState',
    '_content_range_total',
    '_parse_file_size',
]


PAGE_RE = re.compile(r"/s/\d+/[A-Za-z0-9]+/(?P<page>[A-Za-z0-9]+)/")
# Current ExHentai viewer URL: /s/<pToken>/<gid>-<page>  (mirrors Ehviewer_CN_SXJ's
# GalleryPageUrlParser). The 10-hex pToken is what Ehviewer stores in .ehviewer and
# sends as ``imgkey`` to the showpage API.
VIEWER_HREF_RE = re.compile(
    r"/s/(?P<ptoken>[0-9a-f]{10})/(?P<gid>\d+)-(?P<page>\d+)", re.IGNORECASE
)


# ExHentai /s/ viewer page embeds the API session key as ``var showkey="...";``.
SHOWKEY_RE = re.compile(r'var\s+showkey\s*=\s*"([0-9a-z]+)"', re.IGNORECASE)
# ``showpage`` API response fragments (i3 / i6 / i7) carry the resolved image HTML.
SHOWPAGE_IMAGE_RE = re.compile(r'<img[^>]*src="([^"]+)" style', re.IGNORECASE)
SHOWPAGE_SKIP_KEY_RE = re.compile(r"nl\(\s*['\"](.*?)['\"]\s*\)")
SHOWPAGE_ORIGIN_PROMPT_RE = re.compile(
    r'<a href="#" onclick="prompt\(\'Copy the URL below\.\', \'([^\']+)\'\)'
)
SHOWPAGE_ORIGIN_RE = re.compile(r'<a href="([^"]+)fullimg([^"]+)">', re.IGNORECASE)


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