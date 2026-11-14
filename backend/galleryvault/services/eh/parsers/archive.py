"""ExHentai archiver.php page parsing (cost / size / download link)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

# ExHentai archive (archiver.php) page markers.  The page lists two POST forms
# (original / resample) that share the same action URL and differ only in the
# hidden ``dltype``; each carries its own ``Download Cost`` / ``Estimated Size``
# labels.  The GP balance appears near the top ("You have <b>…</b> GP").
__all__ = [
    'ARCHIVER_DOWNLOAD_LINK_RE',
    'ARCHIVER_LOCATION_RE',
    'ARCHIVE_COST_RE',
    'ARCHIVE_FUNDS_RE',
    'ARCHIVE_GP_BALANCE_RE',
    'ARCHIVE_SIZE_RE',
    'ArchiveInfo',
    '_parse_archive_cost',
    '_parse_archive_info',
    '_parse_archive_size',
    '_parse_archiver_download_url',
]


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