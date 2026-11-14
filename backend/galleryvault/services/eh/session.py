from __future__ import annotations

import asyncio
import logging
import time
import weakref
from typing import Any, Self
from urllib.parse import urljoin, urlparse

import httpx

from ...config import Settings, get_settings
from ...logging import log_extra
from ...observability import observe_histogram
from ..eh_parsers import (
    EhClientError,
    EhQuotaExceededError,
    GalleryGoneError,
    _is_auth_failure_page,
    _is_ip_banned_page,
)

logger = logging.getLogger("galleryvault.services.eh_client")

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


ALLOWED_EH_DOMAINS = (
    "e-hentai.org",
    "exhentai.org",
    "ehgt.org",
    "hath.network",
)

# Process-wide limiters. A settings save rebuilds the EhClient and keeps the old
# one alive for a grace period; per-client semaphores would let both clients
# spend a full ExHentai budget at the same time and double our effective
# concurrency. Sharing per running event loop keeps exactly one budget. The
# loop-keyed map keeps test suites (one loop per test) isolated.
_SHARED_LIMITERS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[tuple[str, int], asyncio.Semaphore]
] = weakref.WeakKeyDictionary()

def _is_allowed_eh_host(host: str, base_url: str | None = None) -> bool:
    if not host:
        return False
    host = host.lower()
    if base_url:
        base_host = (urlparse(base_url).hostname or "").lower()
        if base_host and (host == base_host or host.endswith("." + base_host)):
            return True
    return any(host == domain or host.endswith("." + domain) for domain in ALLOWED_EH_DOMAINS)

def _shared_limiter(kind: str, limit: int) -> asyncio.Semaphore:
    """Return the loop-wide semaphore for ``kind`` with the given ``limit``."""
    limit = max(1, int(limit))
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Constructed outside a loop (e.g. sync unit tests): no sharing possible.
        return asyncio.Semaphore(limit)
    per_loop = _SHARED_LIMITERS.get(loop)
    if per_loop is None:
        per_loop = {}
        _SHARED_LIMITERS[loop] = per_loop
    key = (kind, limit)
    semaphore = per_loop.get(key)
    if semaphore is None:
        semaphore = asyncio.Semaphore(limit)
        per_loop[key] = semaphore
    return semaphore

def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None

def _quota_exceeded_error(response: httpx.Response) -> EhQuotaExceededError:
    status = response.status_code
    return EhQuotaExceededError(
        f"ExHentai rate limited (HTTP {status})",
        status_code=status,
        retry_after=_retry_after_seconds(response),
    )



class EhSession:
    """One ExHentai transport session shared by the :class:`EhClient` facade.

    Owns the ``httpx.AsyncClient``, the three loop-wide semaphores and the
    ``_stream_count`` in-flight counter.  ``owner`` is the facade, so instance
    level stubs on ``EhClient._request`` / ``EhClient._raise_for_status`` keep
    affecting the methods implemented here.
    """

    def __init__(
        self,
        owner: Any,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_concurrency: int = 6,
    ) -> None:
        self.owner = owner
        self.settings = settings or get_settings()
        self._owned = client is None
        # A single shared limiter for ALL ExHentai page traffic (gallery pages,
        # gdata, favorites) so the many background workers cannot stack dozens
        # of parallel requests and trip ExHentai's anti-abuse.  The limiter is
        # shared per event loop rather than per client: a settings save rebuilds
        # the client and keeps the old one alive for a grace period, and two
        # independent budgets would double the real concurrency.
        self._semaphore = _shared_limiter("page", max(1, max_concurrency))
        # Image downloads go to the H@H network (hath.network) which is a
        # distributed CDN with its own generous limits — mirroring Ehviewer's
        # 32-thread IO pool, we give images their own, higher limiter instead of
        # sharing the page-fetch budget.
        self._image_semaphore = _shared_limiter(
            "image", max(8, max(1, max_concurrency) * 2)
        )
        # Archive (zip) transfers hit the site itself, not H@H, and are long
        # lived; they get their own small budget so concurrent archives cannot
        # bypass the page limits entirely.
        self._archive_semaphore = _shared_limiter("archive", 2)
        # Long-lived transfers currently in flight (images / covers / archives).
        # ``EhClientManager`` waits for this to reach zero before closing a
        # retired client so a settings rebuild cannot kill a running download.
        self._stream_count = 0
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

        if isinstance(getattr(self.client, "event_hooks", None), dict):
            self.client.event_hooks.setdefault("response", []).append(self._check_redirect_host)

    async def _check_redirect_host(self, response: httpx.Response) -> None:
        """Validate redirect Location host against allowed Eh domains to prevent SSRF."""
        if response.is_redirect:
            location = response.headers.get("Location")
            if location:
                target_url = urljoin(str(response.url), location)
                target_host = (urlparse(target_url).hostname or "").lower()
                if not _is_allowed_eh_host(target_host, self.settings.exhentai_base_url):
                    raise EhClientError(
                        f"Disallowed redirect host in EhClient request: {target_host}"
                    )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owned:
            await self.client.aclose()

    @property
    def in_flight_requests(self) -> int:
        """Number of long-lived transfers (image / cover / archive) still running."""
        return self._stream_count

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        t_wait_start = time.perf_counter()
        async with self._semaphore:
            wait_elapsed = time.perf_counter() - t_wait_start
            observe_histogram("gv_ehclient_semaphore_wait_seconds", wait_elapsed, {"type": "page"})
            t_req_start = time.perf_counter()
            try:
                return await self.client.request(method, url, **kwargs)
            except httpx.HTTPStatusError as exc:
                # ``_request`` normally returns 4xx/5xx responses and callers use
                # ``_raise_for_status``; wrapping here keeps the "EhClient only
                # raises EhClientError" contract if a transport/wrapper raises.
                raise self._status_error(exc.response) from exc
            finally:
                req_elapsed = time.perf_counter() - t_req_start
                observe_histogram("gv_ehclient_request_duration_seconds", req_elapsed, {"method": method})

    @staticmethod
    def _status_error(response: httpx.Response) -> EhClientError:
        """Classify a non-2xx response (quota exhaustion vs. generic failure)."""
        status = response.status_code
        if status in (429, 509):
            return _quota_exceeded_error(response)
        return EhClientError(f"ExHentai returned HTTP {status}")

    def _raise_for_status(
        self, response: httpx.Response, *, gallery_404: bool = False
    ) -> None:
        """Turn HTTP status failures into ``EhClientError`` subclasses."""
        status = response.status_code
        if status in (401, 403) or "login" in str(response.url).lower():
            raise EhClientError("ExHentai authentication is required or expired")
        if status in (429, 509):
            raise _quota_exceeded_error(response)
        if status < 400:
            return
        if status == 404 and gallery_404:
            try:
                path = response.request.url.path
            except RuntimeError:
                path = ""
            if path.startswith("/g/"):
                raise GalleryGoneError("gallery does not exist on ExHentai (404)")
        raise self._status_error(response)

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self.owner._request("GET", url, **kwargs)
            if (
                response.status_code in (401, 403)
                or "login" in str(response.url).lower()
                or _is_auth_failure_page(response.text)
                or _is_ip_banned_page(response.text)
            ):
                raise EhClientError("ExHentai authentication is required or expired")
            self.owner._raise_for_status(response, gallery_404=True)
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
            # ``_request`` already converts these; kept as a defensive catch so a
            # raw httpx status error never escapes the EhClient contract.
            status = exc.response.status_code
            logger.warning(
                "ExHentai returned HTTP error", extra=log_extra(status=status)
            )
            raise self._status_error(exc.response) from exc
