"""Pure parsing helpers for the ExHentai client (no HTTP transport).

Exceptions, data classes and the HTML/URL parsers live here so they can be
imported and unit-tested without pulling in ``httpx`` or the client itself.
``galleryvault.services.eh_client`` re-exports every public symbol, so existing
imports keep working unchanged.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urljoin, urlparse

__all__ = [
    "ARCHIVER_DOWNLOAD_LINK_RE",
    "ARCHIVER_LOCATION_RE",
    "ARCHIVE_COST_RE",
    "ARCHIVE_FUNDS_RE",
    "ARCHIVE_GP_BALANCE_RE",
    "ARCHIVE_SIZE_RE",
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
    "get_fixed_preview_thumb_url",
    "parse_favorite_note",
    "parse_gallery_url",
    "parse_login_state",
    "parse_newer_gallery",
    "parse_search_page",]


GALLERY_RE = re.compile(r"/(?:g|gallery)/(?P<gid>\d+)/(?P<token>[A-Za-z0-9]+)/?")
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
SHOWPAGE_SKIP_KEY_RE = re.compile(r"nl\(\s*['\"](.*?)['\"]\s*\)")
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

# Image Limits box on the ExHentai homepage /home.php:
# Old: "You are currently at <strong>538</strong> towards a limit of <strong>50,000</strong>"
# New: "You are currently at <strong>538</strong> towards your account limit of <strong>50,000</strong>"
# JDownloader parses with: "You are currently at (\d+)" and "towards a limit of (\d+)" (case-insensitive)
IMAGE_LIMIT_RE = re.compile(
    r"You are currently at\s*<[^>]*>\s*([0-9][0-9,]*)\s*</[^>]*>\s*towards\s+(?:your\s+account\s+)?a?\s*limit of\s*<[^>]*>\s*([0-9][0-9,]*)\s*</",
    re.IGNORECASE,
)
IMAGE_LIMIT_SIMPLE_RE = re.compile(r"Image Limit[^0-9]*([0-9][0-9,]*)\s*/\s*([0-9][0-9,]*)", re.IGNORECASE)
# Fallback plain text without tags (e.g. "You are currently at 123 towards a limit of 5000")
IMAGE_LIMIT_PLAIN_RE = re.compile(
    r"You are currently at\s*([0-9][0-9,]*)\s*towards\s+(?:your\s+account\s+)?a?\s*limit of\s*([0-9][0-9,]*)",
    re.IGNORECASE,
)


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


class GalleryReplacedError(EhClientError):
    """The gallery listing points at a newer replacement gid/token."""

    def __init__(
        self,
        old_gid: int,
        new_gid: int,
        new_token: str,
        title: str | None = None,
        title_jpn: str | None = None,
    ) -> None:
        super().__init__(f"gallery {old_gid} replaced by {new_gid}")
        self.old_gid = old_gid
        self.new_gid = new_gid
        self.new_token = new_token
        self.title = title
        self.title_jpn = title_jpn


class EhParseError(EhClientError):
    pass


class EhChallengeError(EhClientError):
    """ExHentai 302 temporary anti-abuse / remoteapi.php challenge."""


class EhQuotaExceededError(EhClientError):
    """ExHentai rate limited the request (HTTP 429/509: IP/account quota).

    Distinct from a transport error: retrying immediately burns more quota, so
    callers should wait ``retry_delay()`` seconds (the server's ``Retry-After``
    when present, otherwise a fixed backoff).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after

    def retry_delay(self, default: float = 60.0, maximum: float = 3600.0) -> float:
        """Seconds to wait before retrying (``Retry-After`` or fixed backoff)."""
        value = self.retry_after if self.retry_after is not None else default
        return max(0.0, min(float(value), float(maximum)))


# Favorites pages advertise every folder in their header/selector as
# ``favorites.php?favcat=N``.  Login/logout/challenge pages never carry those
# markers, so they are the reliable "this is really the favorites page" signal
# for a write that otherwise only returns HTTP 200.
_FAVORITES_PAGE_FAVCAT_RE = re.compile(
    r"favorites\.php\?[^\"'<>\s]*?favcat=(?P<favcat>\d)", re.IGNORECASE
)
_FAVORITES_AUTH_FAILURE_MARKERS = (
    "sad panda",
    "you must be logged in",
    "expired login session",
    "you are not logged in",
)


def _favorites_page_favcats(body: str) -> set[int]:
    return {int(match.group("favcat")) for match in _FAVORITES_PAGE_FAVCAT_RE.finditer(body or "")}


def _is_favorites_auth_failure_page(body: str) -> bool:
    lowered = (body or "").lower()
    return any(marker in lowered for marker in _FAVORITES_AUTH_FAILURE_MARKERS)


def _is_ip_banned_page(body: str) -> bool:
    """Detect the ExHentai IP-banned page."""
    return (
        "Your IP address has been banned" in body
        or "Your IP address is temporarily banned" in body
    )


def _is_auth_failure_page(body: str) -> bool:
    """Detect the ExHentai sadpanda login page.

    These pages answer HTTP 200 with no gallery content, which callers would
    otherwise misread as "gallery deleted". Matching them here keeps auth
    expiry separate from genuine 404s so a dead session cannot mass-mark
    galleries as deleted.
    """
    return "Sad Panda" in body


def _is_exhentai_org_host(host: str | None) -> bool:
    """Check if the given hostname belongs to ExHentai (exhentai.org or *.exhentai.org)."""
    if not host:
        return False
    h = host.strip().lower().rstrip(".")
    return h == "exhentai.org" or h.endswith(".exhentai.org")


# ``/uconfig.php`` is a member-only settings page: a valid session returns the
# full settings form, while a logged-out session returns either the exact
# "expired login session" marker or a generic public/challenge page.  Treating
# "any non-empty body" as logged in (the previous behaviour) reported dead
# cookies as healthy whenever the site answered 200 with something else, so the
# success path now requires a marker only the real settings page carries.
_UCONFIG_POSITIVE_MARKERS = (
    "uconfig.php",
    "user control panel",
    "user configuration",
    "front page settings",
    "thumbnail size",
    "archiver settings",
    'name="uh"',
    "logged in",
)
_UCONFIG_LOGIN_FAILURE_MARKERS = (
    "expired login session",
    "you are not logged in",
    "you must be logged in",
)


def _is_uconfig_page(body: str) -> bool:
    lowered = (body or "").lower()
    return any(marker in lowered for marker in _UCONFIG_POSITIVE_MARKERS)


def parse_login_state(
    body: str,
    member_id: str = "",
    has_cookies: bool = False,
    *,
    host: str | None = None,
) -> str:
    """Classify an ExHentai member-page response into a login state.

    ExHentai answers every session state with HTTP 200 and the public pages
    carry no login markers, so the member-only page body is the reliable
    signal (measured against production cookies):
    - a valid session returns the full settings page, which carries
      ``/uconfig.php`` markers (see ``_UCONFIG_POSITIVE_MARKERS``)
    - an expired/invalid session returns exactly ``expired login session``
    - an IP-banned page indicates the IP address is banned
    - a Sad-Panda page has no content at all
    - an empty or blank HTTP 200 on exhentai.org (*.exhentai.org) indicates
      the account lacks ExHentai access (no igneous / no exhentai permission)
    - an empty body on other hosts (e.g. e-hentai.org, unknown) is an anti-bot
      challenge or transient glitch, classified as ``failed``
    - any other non-empty body without the settings-page markers is an
      anti-abuse/redirect page, classified as ``failed`` rather than ``ok``

    Returns one of ``ok`` / ``not_logged_in`` / ``no_exhentai_access`` /
    ``ip_banned`` / ``failed``.  An empty body on exhentai.org is classified
    ``no_exhentai_access``; on other hosts or host=None it is classified
    ``failed`` (a retry, not a cookie reset).  ``member_id`` / ``has_cookies``
    are kept for signature compatibility but are no longer part of the
    classification.
    """
    if _is_ip_banned_page(body):
        return "ip_banned"
    if _is_auth_failure_page(body):
        return "no_exhentai_access"
    if not body or not body.strip():
        return "no_exhentai_access" if _is_exhentai_org_host(host) else "failed"
    lowered = body.lower()
    if any(marker in lowered for marker in _UCONFIG_LOGIN_FAILURE_MARKERS):
        return "not_logged_in"
    if _is_uconfig_page(body):
        return "ok"
    return "failed"


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
    replaced_by: tuple[int, str] | None = None


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


@dataclass
class EhSearchResult:
    items: list[SearchGallery]
    next_cursor: str | None = None
    state: str = "ok"


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
    # ExHentai emits either quote style; matching only ``"`` silently stopped
    # after page 1 if the markup changed, truncating favorites.
    match = re.search(r"var\s+nexturl\s*=\s*[\"']([^\"']*)[\"']", body)
    if not match:
        return ""
    value = match.group(1).strip()
    if not value or "next=" not in value:
        return ""
    return value


_NEXT_CURSOR_RE = re.compile(r"^\d+(-\d+)?$")
_TOPLIST_CURSOR_RE = re.compile(r"^\d+$")


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
    from ..scanners.base import normalize_category

    return normalize_category(_text(match.group(1)))


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
