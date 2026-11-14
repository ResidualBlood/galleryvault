from __future__ import annotations

import html
import logging
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from ...logging import log_extra
from ..eh_parsers import (
    ARCHIVE_GP_BALANCE_RE,
    ARCHIVER_LOCATION_RE,
    IMAGE_LIMIT_PLAIN_RE,
    IMAGE_LIMIT_RE,
    IMAGE_LIMIT_SIMPLE_RE,
    ArchiveExpiredError,
    ArchiveInfo,
    EhClientError,
    _content_range_total,
    _is_auth_failure_page,
    _is_ip_banned_page,
    _parse_archive_info,
    _parse_archiver_download_url,
)
from .session import _is_allowed_eh_host

logger = logging.getLogger("galleryvault.services.eh_client")

async def fetch_archive_info(client, gid: int, token: str) -> ArchiveInfo:
    """Read the archiver.php page: GP funds + original/resample costs/sizes.

    Read-only — nothing is charged here (charging happens on the POST in
    ``request_archive``).  Uses the shared page-fetch budget.
    """
    response = await client._get(
        f"/archiver.php?gid={int(gid)}&token={token}",
        headers={"Referer": f"/g/{int(gid)}/{token}/"},
    )
    return _parse_archive_info(response.text)

async def fetch_gp_balance(client) -> int | None:
    """Read the current GP balance from the GP exchange page.

    archiver.php no longer shows ``You have X GP``, so the balance is
    taken from the exchange page's "Sell GP" box (``Available: N kGP``,
    displayed in thousands).  Returns None when the page is unreachable
    or the balance cannot be parsed.
    """
    try:
        response = await client._get("https://e-hentai.org/exchange.php?t=gp")
    except EhClientError:
        return None
    match = ARCHIVE_GP_BALANCE_RE.search(response.text)
    if not match:
        return None
    return int(float(match.group(1).replace(",", "")) * 1000)

def _parse_image_limits(client, body: str) -> dict[str, int] | None:
    """Parse ``You are currently at X towards a limit of Y`` from a homepage body.

    Handles old/new markup with or without ``<strong>`` tags and plain text.
    Returns ``{"current": int, "limit": int}`` or None.
    """
    for pattern in (IMAGE_LIMIT_RE, IMAGE_LIMIT_SIMPLE_RE, IMAGE_LIMIT_PLAIN_RE):
        match = pattern.search(body)
        if match:
            try:
                current = int(match.group(1).replace(",", ""))
                limit = int(match.group(2).replace(",", ""))
                return {"current": current, "limit": limit}
            except (ValueError, IndexError):
                continue
    return None

async def fetch_image_limits(client) -> dict[str, int] | None:
    """Read current / max image limits from the ExHentai homepage (home.php).

    The homepage box says "You are currently at X towards a limit of Y"
    (old) or "towards your account limit of Y" (new). Returns
    ``{"current": int, "limit": int}`` or None if unreachable, not logged
    in (Sad Panda), or the new IP-based quota hides the limit (post-2024).
    """
    for path in ("/home.php", "/"):
        try:
            response = await client._get(path)
        except EhClientError:
            continue
        body = response.text
        if _is_auth_failure_page(body) or _is_ip_banned_page(body):
            return None
        parsed = client._parse_image_limits(body)
        if parsed:
            return parsed
    return None

async def request_archive(client, url: str, dltype: str) -> str:
    """Ask ExHentai to build the archive zip and return its download URL.

    ``dltype`` is ``org`` or ``res``.  This POST is what actually spends GP,
    so the executor persists the returned URL and never re-calls this for an
    already-requested archive.  Mirrors SXJ's ``downloadArchiver``: follow
    the ``document.location`` hop, then parse the zip link.
    """
    if dltype not in {"org", "res"}:
        raise ValueError("dltype must be 'org' or 'res'")
    dlcheck = (
        "Download Original Archive"
        if dltype == "org"
        else "Download Resample Archive"
    )
    origin = client.settings.exhentai_base_url.rstrip("/")
    response = await client._request(
        "POST",
        url,
        data={"dltype": dltype, "dlcheck": dlcheck},
        headers={"Referer": url, "Origin": origin},
    )
    client._raise_for_status(response)
    body = response.text
    direct = _parse_archiver_download_url(body)
    if direct:
        return urljoin(str(response.url), direct)
    location = ARCHIVER_LOCATION_RE.search(body)
    if not location:
        if _is_auth_failure_page(body) or _is_ip_banned_page(body):
            raise EhClientError("ExHentai authentication is required or expired")
        raise EhClientError("ExHentai archiver request returned no download link")
    continue_url = html.unescape(location.group(1))
    confirmation = await client._get(continue_url)
    link = _parse_archiver_download_url(confirmation.text)
    if not link:
        raise EhClientError("ExHentai archiver confirmation page has no download link")
    return urljoin(str(confirmation.url), link)

async def download_archive(
    client, url: str, dest: Path, cb: Callable[[int, int | None], object] | None = None
) -> int:
    """Stream an archive zip to ``dest`` with Range resume support.

    Archives are served by ExHentai itself (not H@H nodes) and are long
    lived, so they take their own small budget (``_archive_semaphore``)
    instead of bypassing the limiters entirely, and the image chain's
    throughput watchdog (warm-up + minimum average speed) applies here too.
    There is deliberately no total wall-clock budget: a multi-GB archive can
    legitimately take many minutes, while a stalled or trickling transfer is
    still aborted.  ``cb(downloaded, total)`` receives byte progress.
    Returns the final total size.
    """
    host = (urlparse(url).hostname or "").lower()
    if not _is_allowed_eh_host(host, client.settings.exhentai_base_url):
        raise EhClientError(f"Disallowed host in archive URL: {host}")
    await client._archive_semaphore.acquire()
    client._stream_count += 1
    try:
        return await client._stream_archive(url, dest, cb)
    finally:
        client._stream_count -= 1
        client._archive_semaphore.release()

async def _stream_archive(
    client, url: str, dest: Path, cb: Callable[[int, int | None], object] | None = None
) -> int:
    offset = dest.stat().st_size if dest.is_file() else 0
    headers = {"Referer": client.settings.exhentai_base_url.rstrip("/") + "/"}
    if offset > 0:
        headers["Range"] = f"bytes={offset}-"
    timeout = httpx.Timeout(120.0, read=30.0)
    try:
        async with client.client.stream(
            "GET", url, headers=headers, timeout=timeout
        ) as response:
            if response.status_code in (401, 403) or "login" in str(
                response.url
            ).lower():
                raise EhClientError(
                    "ExHentai authentication is required or expired"
                )
            if response.status_code in (429, 509):
                raise EhClientError(
                    f"ExHentai rate limited (HTTP {response.status_code})"
                )
            if response.status_code == 416:
                total = _content_range_total(response.headers.get("content-range"))
                if total is not None and offset == total:
                    return total
                # Oversized or truncated partial: 416 with offset != total indicates
                # corrupt/oversized local file. Clear so next attempt restarts cleanly.
                if offset != 0:
                    logger.warning(
                        "archive download 416 range error, clearing corrupt partial file",
                        extra=log_extra(dest=str(dest), offset=offset, total=total),
                    )
                    dest.unlink(missing_ok=True)
                raise EhClientError("ExHentai archive range is not satisfiable")
            if response.status_code == 200:
                if offset > 0:
                    # Server ignored the Range header: restart from scratch.
                    dest.unlink(missing_ok=True)
                    offset = 0
            elif response.status_code != 206:
                raise client._status_error(response)
            content_length = response.headers.get("content-length") or ""
            total = _content_range_total(
                response.headers.get("content-range")
            ) or (offset + int(content_length) if content_length.isdigit() else None)
            downloaded = offset
            last_cb_time = 0.0
            last_cb_bytes = downloaded
            mode = "ab" if offset > 0 else "wb"
            started = time.monotonic()
            # Same watchdog as the image chain: the 30s read timeout only
            # fires when a transfer stalls completely, so a node trickling a
            # few KB/s could hold a worker (and its archive slot) forever.
            # No total budget here — archives are legitimately large.
            warmup = max(1, int(client.settings.image_slow_warmup_seconds))
            min_speed = max(1, int(client.settings.image_min_speed_kb_s)) * 1024
            with dest.open(mode) as handle:
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)
                    downloaded += len(chunk)
                    elapsed = time.monotonic() - started
                    if elapsed > warmup:
                        transferred = downloaded - offset
                        if transferred / elapsed < min_speed:
                            raise EhClientError(
                                "ExHentai archive transfer throttled "
                                f"({transferred / elapsed / 1024:.0f} KB/s < "
                                f"{int(client.settings.image_min_speed_kb_s)} KB/s)"
                            )
                    if cb is not None:
                        now = time.monotonic()
                        if (
                            now - last_cb_time >= 0.2
                            or (total is not None and downloaded == total)
                            or (downloaded - last_cb_bytes >= 1024 * 1024)
                        ):
                            await cb(downloaded, total)
                            last_cb_time = now
                            last_cb_bytes = downloaded
                if cb is not None and last_cb_bytes != downloaded:
                    await cb(downloaded, total)
        if total is not None and downloaded != total:
            raise EhClientError("ExHentai archive download was incomplete")
        return total if total is not None else downloaded
    except httpx.HTTPError as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (404, 410):
            raise ArchiveExpiredError("archive URL is expired or not found") from exc
        logger.warning(
            "archive download request failed",
            extra=log_extra(error=type(exc).__name__),
        )
        raise EhClientError("ExHentai archive download failed") from exc
