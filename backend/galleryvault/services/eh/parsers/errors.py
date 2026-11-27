"""Exceptions and HTML page classification for the ExHentai client.

Pure: no I/O, no HTTP transport, no app/db imports."""

from __future__ import annotations

import re

# Image Limits box on the ExHentai homepage /home.php:
# Old: "You are currently at <strong>538</strong> towards a limit of <strong>50,000</strong>"
# New: "You are currently at <strong>538</strong> towards your account limit of <strong>50,000</strong>"
# JDownloader parses with: "You are currently at (\d+)" and "towards a limit of (\d+)" (case-insensitive)
__all__ = [
    'IMAGE_LIMIT_PLAIN_RE',
    'IMAGE_LIMIT_RE',
    'IMAGE_LIMIT_SIMPLE_RE',
    '_FAVORITES_AUTH_FAILURE_MARKERS',
    '_FAVORITES_PAGE_FAVCAT_RE',
    '_UCONFIG_LOGIN_FAILURE_MARKERS',
    '_UCONFIG_POSITIVE_MARKERS',
    'ArchiveExpiredError',
    'EhAuthRequiredError',
    'EhBannedError',
    'EhChallengeError',
    'EhClientError',
    'EhImageSlowError',
    'EhParseError',
    'EhQuotaExceededError',
    'GalleryGoneError',
    'GalleryReplacedError',
    '_favorites_page_favcats',
    '_is_auth_failure_page',
    '_is_exhentai_org_host',
    '_is_favorites_auth_failure_page',
    '_is_ip_banned_page',
    '_is_uconfig_page',
    'parse_login_state',
]


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


class EhBannedError(EhClientError):
    """ExHentai answered with its IP-banned page.

    Kept distinct from the generic auth error so online endpoints can pass
    ``state=banned`` through to the client instead of asking the user to
    re-login.
    """


class EhAuthRequiredError(EhClientError):
    """ExHentai requires a valid session (Sad Panda / expired login)."""


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