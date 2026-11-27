from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from urllib.parse import urljoin, urlparse

import httpx

from ...logging import log_extra
from ...observability import observe_histogram
from ..eh_parsers import EhClientError, EhImageSlowError, GalleryGoneError, parse_gallery_url
from .session import _is_allowed_eh_host

logger = logging.getLogger("galleryvault.services.eh_client")

async def download_image(client, url: str) -> bytes:
    content, _ = await client.download_image_with_metadata(url)
    return content

async def fetch_gallery_cover(client, gid: int | str, token: str | None = None) -> tuple[bytes, str]:
    """Download the gallery cover image, returning ``(bytes, content_type)``."""
    if token is None:
        gid, token = parse_gallery_url(str(gid), client.settings.exhentai_base_url)
    response = await client._get(f"/g/{int(gid)}/{token}/")
    match = re.search(
        r'id=["\']cover["\'][^>]*src=["\']([^"\']+)["\']', response.text, re.IGNORECASE
    )
    if not match:
        match = re.search(
            r'<div[^>]*id=["\']gd1["\'][^>]*>.*?'
            r'background[^:]*:\s*(?:transparent\s*)?url\(["\']?([^"\')]+)["\']?\)',
            response.text,
            re.IGNORECASE | re.DOTALL,
        )
    if not match:
        match = re.search(
            r'<div[^>]*id=["\']gd1["\'][^>]*>.*?<img[^>]+src=["\']([^"\']+)["\']',
            response.text,
            re.IGNORECASE | re.DOTALL,
        )
    if not match:
        raise GalleryGoneError("gallery has no cover")
    cover_url = urljoin(str(response.url), html.unescape(match.group(1)))
    # Route cover through the correct limiter (H@H images vs site pages),
    # mirroring download_image_with_metadata's host-based budget.
    host = (urlparse(cover_url).hostname or "").lower()
    if not _is_allowed_eh_host(host, client.settings.exhentai_base_url):
        raise EhClientError(f"Disallowed host in gallery cover URL: {host}")
    use_image_budget = "hath.network" in host or host.endswith(".ehgt.org")
    semaphore = client._image_semaphore if use_image_budget else client._semaphore
    t_wait_start = time.perf_counter()
    client._stream_count += 1
    try:
        async with semaphore:
            wait_elapsed = time.perf_counter() - t_wait_start
            observe_histogram(
                "gv_ehclient_semaphore_wait_seconds",
                wait_elapsed,
                {"type": "image" if use_image_budget else "page"},
            )
            client._session.ensure_redirect_hook()
            cover_response = await client.client.get(
                cover_url,
                headers={"Referer": str(response.url)},
                timeout=httpx.Timeout(120.0, read=30.0),
                follow_redirects=True,
            )
    finally:
        client._stream_count -= 1
    for redirect_resp in getattr(cover_response, "history", []):
        loc = redirect_resp.headers.get("Location")
        if loc:
            redirect_url = urljoin(str(redirect_resp.url), loc)
            redirect_host = (urlparse(redirect_url).hostname or "").lower()
            if not _is_allowed_eh_host(redirect_host, client.settings.exhentai_base_url):
                raise EhClientError(
                    f"Disallowed redirect host in gallery cover: {redirect_host}"
                )
    final_host = (urlparse(str(cover_response.url)).hostname or "").lower()
    if not _is_allowed_eh_host(final_host, client.settings.exhentai_base_url):
        raise EhClientError(f"Disallowed host in gallery cover response: {final_host}")
    if cover_response.status_code in (401, 403) or "login" in str(cover_response.url).lower():
        raise EhClientError("ExHentai authentication is required or expired")
    client._raise_for_status(cover_response)
    if len(cover_response.content) < 200:
        # ExHentai answers galleries without a usable cover (or ones that
        # need a different H@H setup) with a 1x1 placeholder GIF.
        raise GalleryGoneError("gallery has no usable cover")
    return (
        cover_response.content,
        cover_response.headers.get("content-type", "image/jpeg").split(";")[0].strip(),
    )

async def download_image_with_metadata(client, url: str) -> tuple[bytes, str]:
    host = (urlparse(url).hostname or "").lower()
    if not _is_allowed_eh_host(host, client.settings.exhentai_base_url):
        raise EhClientError(f"Disallowed host in image URL: {host}")
    # H@H image nodes (hath.network) are a distributed CDN with loose
    # limits — use the higher image limiter. Original-quality downloads
    # against the exhentai.org host stay on the page-fetch budget so we
    # don't trip anti-abuse on the site itclient.
    use_image_budget = "hath.network" in host or host.endswith(".ehgt.org")
    semaphore = client._image_semaphore if use_image_budget else client._semaphore
    t_wait_start = time.perf_counter()
    client._stream_count += 1
    try:
        async with semaphore:
            wait_elapsed = time.perf_counter() - t_wait_start
            observe_histogram(
                "gv_ehclient_semaphore_wait_seconds",
                wait_elapsed,
                {"type": "image" if use_image_budget else "page"},
            )
            # read=30s acts as a zero-progress watchdog (Ehviewer_CN_SXJ
            # aborts stalled downloads after ~3s of no bytes): a hanging H@H
            # node fails fast instead of holding the worker until the
            # overall timeout. 30s gives large images (GIF/animated) room
            # to resume after a node hiccup; the total budget below still
            # bounds the whole transfer.
            timeout = httpx.Timeout(120.0, read=30.0)
            # A throttled H@H node answers image requests with a tiny
            # "509" placeholder instead of the real file. Ehviewer_CN_SXJ
            # detects it by URL suffix; without the check the placeholder
            # would be saved as a legit page.
            if urlparse(url).path.rstrip("/").endswith(("/509.gif", "/509s.gif")):
                raise EhImageSlowError("ExHentai rate limited (509 placeholder)")
            # ``image_download_timeout_seconds`` is an end-to-end deadline
            # for the whole image transfer, not just a per-chunk budget:
            # the httpx timeouts above only bound individual phases, so a
            # node that never sends response headers (or trickles bytes
            # just under the read watchdog) would otherwise hold the
            # worker indefinitely.  Cancellation unwinds through the
            # ``stream`` context manager, which closes the response.
            deadline = float(client.settings.image_download_timeout_seconds)
            try:
                async with asyncio.timeout(deadline):
                    async with client.client.stream(
                        "GET",
                        url,
                        headers={
                            "Referer": client.settings.exhentai_base_url.rstrip("/") + "/"
                        },
                        timeout=timeout,
                    ) as response:
                        if response.status_code in (429, 509):
                            raise EhClientError(
                                f"ExHentai rate limited (HTTP {response.status_code})"
                            )
                        if response.status_code in (401, 403):
                            raise EhClientError(
                                "ExHentai authentication is required or expired"
                            )
                        response.raise_for_status()
                        # Anti-hijack guard (Ehviewer_CN_SXJ mirrors this): if a
                        # redirect or a MITM sent us to a host outside ExHentai's
                        # own CDN/infra, the response is not the requested image.
                        final_host = (
                            urlparse(str(response.url)).hostname or ""
                        ).lower()
                        if (
                            final_host != host
                            and not final_host.endswith("hath.network")
                            and not final_host.endswith(".ehgt.org")
                            and final_host not in {"exhentai.org", "e-hentai.org"}
                        ):
                            raise EhClientError(
                                "image download redirected to unexpected host: "
                                f"{final_host}"
                            )
                        chunks: list[bytes] = []
                        total = 0
                        started = time.monotonic()
                        # Watchdogs for a slow-but-alive H@H node: the 30s read
                        # timeout only fires when no bytes arrive at all, so a node
                        # trickling a few KB/s would otherwise hold the worker
                        # indefinitely.  Enforce a total wall-clock budget plus a
                        # minimum average throughput once past the warm-up window.
                        budget = max(
                            1, int(client.settings.image_download_timeout_seconds)
                        )
                        warmup = max(
                            1, int(client.settings.image_slow_warmup_seconds)
                        )
                        min_speed = (
                            max(1, int(client.settings.image_min_speed_kb_s)) * 1024
                        )
                        async for chunk in response.aiter_bytes():
                            chunks.append(chunk)
                            total += len(chunk)
                            elapsed = time.monotonic() - started
                            if elapsed > budget:
                                raise EhImageSlowError(
                                    f"image download exceeded {budget}s budget "
                                    f"({total / max(elapsed, 1e-6) / 1024:.0f} KB/s)"
                                )
                            if elapsed > warmup and total / elapsed < min_speed:
                                raise EhImageSlowError(
                                    "H@H node throttled "
                                    f"({total / elapsed / 1024:.0f} KB/s < "
                                    f"{int(client.settings.image_min_speed_kb_s)} KB/s)"
                                )
                        content_type = (
                            response.headers.get("content-type", "")
                            .split(";")[0]
                            .strip()
                        )
                        if not chunks or content_type.lower().startswith("text/"):
                            raise EhClientError("image response was not an image")
                        content_length = response.headers.get("content-length")
                        if (
                            content_length is not None
                            and content_length.isdigit()
                            and total != int(content_length)
                        ):
                            # Truncated by a proxy or a server hiccup — surface
                            # it as a retryable failure instead of writing a
                            # corrupt page.
                            raise EhClientError("image download was incomplete")
                        return b"".join(chunks), content_type
            except TimeoutError as exc:
                # Same exception type as the in-loop budget check so callers
                # keep classifying this as a retryable slow node.
                raise EhImageSlowError(
                    f"image download exceeded {deadline:g}s budget "
                    "(end-to-end deadline)"
                ) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "image download request failed",
            extra=log_extra(error=type(exc).__name__, host=host),
        )
        raise EhClientError(
            f"ExHentai image download failed: {type(exc).__name__} on {host}"
        ) from exc
    finally:
        client._stream_count -= 1
