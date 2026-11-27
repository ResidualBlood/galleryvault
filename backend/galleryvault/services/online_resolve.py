"""Resolve one online-reader page to a short-lived direct H@H image URL.

The reader does not proxy image bytes: a single ExHentai ``showpage`` call
yields an H@H URL that the browser fetches directly.  This module keeps the
server-side cost at one page-budget request per page and never touches the
image semaphore.

Cache / concurrency contract (see PLAN §3.4):

* the per-gallery ``showkey`` and the preview-page pTokens are cached so the
  steady state is exactly one ``showpage`` per page;
* resolved URLs live for 600 s (inside the 900 s keystamp window); a cached
  response is returned without any upstream request;
* identical concurrent requests share one in-flight upstream call;
* ``retry>=1`` re-fetches the viewer HTML with ``nl=<skip key>`` so ExHentai
  picks another H@H node (showpage itself cannot switch nodes);
* ``/509.gif`` / ``/509s.gif`` placeholders surface as ``image_limit`` and are
  never cached;
* image hosts outside the Eh allow-list are rejected before the URL leaves the
  API.  Image URLs, showkeys and pTokens are never logged.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..app.exceptions import EhClientUnavailableError
from ..app.state import app_state
from .eh_client import (
    EhAuthRequiredError,
    EhBannedError,
    EhChallengeError,
    EhClientError,
    EhQuotaExceededError,
    GalleryPageData,
    ShowkeyState,
    _is_allowed_eh_host,
)

logger = logging.getLogger(__name__)

# Resolved URLs expire well inside the 900 s keystamp window so a reader that
# flips back to a page never has to hit an already-dead H@H signature.
RESOLVE_TTL_SECONDS = 600.0
# The showkey / pTokens only change when ExHentai rotates the session; a
# longer TTL avoids paying for a preview page on every reader session.
SHOWKEY_TTL_SECONDS = 1800.0
PTOKEN_TTL_SECONDS = 1800.0
_CACHE_MAX = 256
_PREVIEW_PAGE_SIZE = 20

_RESOLVE_CACHE = "eh_online_resolve_cache"
_SHOWKEY_CACHE = "eh_online_showkey_cache"
_PTOKEN_CACHE = "eh_online_ptoken_cache"
_INFLIGHT = "eh_online_resolve_inflight"
_LIMITERS = "eh_online_reader_limiters"

# H@H image names embed the served dimensions as ``-<size>-<w>-<h>-wbp``.
_IMAGE_DIM_RE = re.compile(r"-(\d+)-(\d+)-(?:wbp|p)(?:/|$)", re.IGNORECASE)
_LIMIT_SUFFIXES = ("/509.gif", "/509s.gif")


class OnlineResolveError(Exception):
    """A resolve failure the router maps to ``{detail: {code}}``."""

    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def _now() -> float:
    return time.monotonic()


def _bucket(name: str) -> dict[Any, Any]:
    bucket = app_state.extra.get(name)
    if not isinstance(bucket, dict):
        bucket = {}
        app_state.extra[name] = bucket
    return bucket


def _cache_get(bucket_name: str, key: tuple[Any, ...]) -> Any | None:
    bucket = _bucket(bucket_name)
    hit = bucket.get(key)
    if not hit:
        return None
    expires, payload = hit
    if float(expires) <= _now():
        bucket.pop(key, None)
        return None
    return payload


def _cache_set(
    bucket_name: str, key: tuple[Any, ...], payload: Any, ttl: float
) -> None:
    bucket = _bucket(bucket_name)
    now = _now()
    if len(bucket) >= _CACHE_MAX:
        for stale in [k for k, (exp, _) in bucket.items() if float(exp) <= now]:
            bucket.pop(stale, None)
        while len(bucket) >= _CACHE_MAX:
            oldest = min(bucket, key=lambda item: bucket[item][0])
            bucket.pop(oldest, None)
    bucket[key] = (now + ttl, payload)


def _showkey_get(gid: int, token: str) -> str | None:
    value = _cache_get(_SHOWKEY_CACHE, (gid, token))
    return str(value) if value else None


def _showkey_set(gid: int, token: str, showkey: str) -> None:
    if showkey:
        _cache_set(_SHOWKEY_CACHE, (gid, token), showkey, SHOWKEY_TTL_SECONDS)


def _ptokens_get(gid: int, token: str, preview_page: int) -> dict[str, Any] | None:
    value = _cache_get(_PTOKEN_CACHE, (gid, token, preview_page))
    return value if isinstance(value, dict) else None


def _ptokens_set(
    gid: int, token: str, preview_page: int, value: dict[str, Any]
) -> None:
    _cache_set(_PTOKEN_CACHE, (gid, token, preview_page), value, PTOKEN_TTL_SECONDS)


def _reader_limit() -> int:
    try:
        from ..app.dependencies import get_current_settings

        configured = getattr(get_current_settings(), "online_reader_concurrency", 3)
        return max(1, int(configured or 3))
    except Exception:  # noqa: BLE001
        return 3


def _reader_limiter(limit: int) -> asyncio.Semaphore:
    limiters = _bucket(_LIMITERS)
    semaphore = limiters.get(limit)
    if semaphore is None:
        semaphore = asyncio.Semaphore(limit)
        limiters[limit] = semaphore
    return semaphore


def _state_code(exc: Exception) -> str:
    if isinstance(exc, EhBannedError):
        return "banned"
    if isinstance(exc, EhAuthRequiredError):
        return "auth"
    if isinstance(exc, EhChallengeError):
        return "challenge"
    return "upstream"


def _translate_error(exc: Exception) -> OnlineResolveError:
    if isinstance(exc, EhQuotaExceededError):
        return OnlineResolveError(429, "image_limit")
    if isinstance(exc, (EhBannedError, EhAuthRequiredError, EhChallengeError)):
        return OnlineResolveError(503, _state_code(exc))
    return OnlineResolveError(502, "upstream")


def _base_url(client: Any) -> str:
    settings = getattr(client, "settings", None)
    configured = getattr(settings, "exhentai_base_url", None)
    return str(configured or "https://exhentai.org").rstrip("/")


def _viewer_url(client: Any, gid: int, p_token: str, page: int) -> str:
    return f"{_base_url(client)}/s/{p_token}/{gid}-{page}"


def _with_nl(url: str, skip_key: str) -> str:
    parsed = urlparse(url)
    pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "nl"
    ]
    pairs.append(("nl", skip_key))
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(pairs),
            parsed.fragment,
        )
    )


def _is_509_placeholder(url: str) -> bool:
    return urlparse(url).path.rstrip("/").endswith(_LIMIT_SUFFIXES)


def _image_dimensions(url: str) -> tuple[int, int]:
    match = _IMAGE_DIM_RE.search(urlparse(url).path)
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


async def _page_token(client: Any, gid: int, token: str, page: int) -> str:
    """Return the viewer pToken for ``page`` (cached per preview page)."""
    preview_page = (page - 1) // _PREVIEW_PAGE_SIZE
    cached = _ptokens_get(gid, token, preview_page)
    if cached is None:
        try:
            preview = await client.fetch_gallery_preview_page(gid, token, preview_page)
        except (EhClientError, EhClientUnavailableError) as exc:
            raise _translate_error(exc) from exc
        cached = {
            "ptokens": dict(preview.ptokens),
            "total": preview.total,
        }
        _ptokens_set(gid, token, preview_page, cached)
    total = cached.get("total")
    if total is not None and page > int(total):
        raise OnlineResolveError(404, "page_out_of_range")
    p_token = (cached.get("ptokens") or {}).get(page)
    if not p_token:
        # A missing token on a page the gallery says exists means the preview
        # markup drifted; refusing is safer than sending a bogus imgkey.
        if total is None:
            raise OnlineResolveError(502, "upstream")
        raise OnlineResolveError(404, "page_out_of_range")
    return str(p_token)


async def _resolve_with_client(
    client: Any, gid: int, token: str, page: int, retry: int
) -> tuple[dict[str, Any], str | None]:
    p_token = await _page_token(client, gid, token, page)
    viewer_url = _viewer_url(client, gid, p_token, page)
    showkey = ShowkeyState()
    showkey.value = _showkey_get(gid, token)

    async def _call(url: str, state: ShowkeyState) -> Any:
        data = GalleryPageData(index=page - 1, url=url, token=p_token)
        try:
            return await client.resolve_page(gid, data, state)
        except (EhClientError, EhClientUnavailableError) as exc:
            raise _translate_error(exc) from exc

    if retry > 0:
        cached = _cache_get(_RESOLVE_CACHE, (gid, token, page))
        skip_key = (cached or {}).get("skip_hath_key")
        if skip_key:
            html_state = ShowkeyState()
            resolved = await _call(_with_nl(viewer_url, str(skip_key)), html_state)
            showkey = html_state
        else:
            # No cached skip key (first-ever request was already a retry): one
            # normal resolution discovers ``nl``, then the HTML re-fetch switches
            # the node.  Two requests only in this cold edge case.
            first = await _call(viewer_url, showkey)
            skip_key = first.skip_hath_key
            if skip_key:
                html_state = ShowkeyState()
                resolved = await _call(_with_nl(viewer_url, str(skip_key)), html_state)
                showkey = html_state
            else:
                resolved = first
    else:
        resolved = await _call(viewer_url, showkey)

    if showkey.value:
        _showkey_set(gid, token, str(showkey.value))

    image_url = str(getattr(resolved, "image_url", "") or "")
    if not image_url:
        raise OnlineResolveError(502, "upstream")
    if _is_509_placeholder(image_url):
        raise OnlineResolveError(429, "image_limit")
    host = (urlparse(image_url).hostname or "").lower()
    if not _is_allowed_eh_host(host, _base_url(client)):
        raise OnlineResolveError(502, "host_not_allowed")

    width, height = _image_dimensions(image_url)
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=RESOLVE_TTL_SECONDS)
    ).isoformat()
    response = {
        "state": "ok",
        "page": page,
        "url": image_url,
        "width": width,
        "height": height,
        "expires_at": expires_at,
    }
    return response, getattr(resolved, "skip_hath_key", None)


async def _resolve_and_cache(
    client_mgr: Any, gid: int, token: str, page: int, retry: int
) -> dict[str, Any]:
    async with _reader_limiter(_reader_limit()):
        try:
            async with client_mgr.client_context() as client:
                response, skip_key = await _resolve_with_client(
                    client, gid, token, page, retry
                )
        except OnlineResolveError:
            raise
        except (EhClientError, EhClientUnavailableError) as exc:
            raise _translate_error(exc) from exc
    _cache_set(
        _RESOLVE_CACHE,
        (gid, token, page),
        {"response": response, "skip_hath_key": skip_key},
        RESOLVE_TTL_SECONDS,
    )
    return response


async def resolve_online_page(
    client_mgr: Any, gid: int, token: str, page: int, retry: int = 0
) -> dict[str, Any]:
    """Resolve one reader page, reusing caches and coalescing concurrent calls."""
    gid = int(gid)
    page = int(page)
    retry = max(0, int(retry))
    if page <= 0:
        raise OnlineResolveError(404, "page_out_of_range")

    token = str(token)
    if retry == 0:
        cached = _cache_get(_RESOLVE_CACHE, (gid, token, page))
        if cached is not None:
            return dict(cached["response"])

    inflight = _bucket(_INFLIGHT)
    key = (gid, token, page, retry > 0)
    task = inflight.get(key)
    if task is None:
        task = asyncio.ensure_future(
            _resolve_and_cache(client_mgr, gid, token, page, retry)
        )
        inflight[key] = task

        def _cleanup(done: asyncio.Future[Any]) -> None:
            if inflight.get(key) is done:
                inflight.pop(key, None)
            if not done.cancelled():
                # Consume the exception so a cancelled caller cannot leave an
                # "exception was never retrieved" warning behind.
                done.exception()

        task.add_done_callback(_cleanup)
    return dict(await asyncio.shield(task))
