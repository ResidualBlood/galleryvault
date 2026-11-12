"""Disk-backed fallback cache for the online reader's proxied page images.

The browser normally fetches H@H images directly (see
:mod:`galleryvault.services.online_resolve`); this module only backs the
per-device manual fallback where the browser cannot reach the image hosts.
It keeps the server-side cost predictable:

* cache key is ``(gid, page)`` under ``<thumbnail_cache_dir>/../online``;
* bytes are written through a unique temp file + ``replace()`` so concurrent
  misses for the same key can never publish a half-written image;
* concurrent requests for the same key share one resolve + one download;
* the resolve phase uses the same ``online_reader_concurrency`` semaphore as
  the direct reader, and the download phase goes through
  ``download_image_with_metadata`` so the client's existing image/page
  semaphore budget is never bypassed;
* 509 placeholders and upstream quota responses surface as ``image_limit``
  and are never written to disk.

ETag / 304 handling lives in the router; this module only exposes the file
path and the stat-based ETag helper.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..app.exceptions import EhClientUnavailableError, EhQuotaExceededError
from ..app.state import app_state
from .eh_client import (
    EhAuthRequiredError,
    EhBannedError,
    EhChallengeError,
    EhClientError,
    _is_allowed_eh_host,
)
from .online_resolve import (
    OnlineResolveError,
    _reader_limit,
    _reader_limiter,
    resolve_online_page,
)

_INFLIGHT = "eh_online_image_inflight"
_LIMIT_SUFFIXES = ("/509.gif", "/509s.gif")


def online_cache_dir(settings: Any) -> Path:
    """Return the proxy image cache root (sibling of the thumbnail cache)."""
    thumbnail_dir = getattr(settings, "thumbnail_cache_dir", None)
    if not thumbnail_dir:
        thumbnail_dir = "/gv-cache/thumbs"
    return Path(thumbnail_dir).parent / "online"


def page_cache_path(root: Path, gid: int, page: int) -> Path:
    return Path(root) / str(int(gid)) / f"{int(page)}.img"


def cache_etag(path: Path) -> str | None:
    """Stable ETag from the cached file's identity, or ``None`` if absent."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return f'"{path.parent.name}-{path.stem}-{int(stat.st_mtime_ns)}-{stat.st_size}"'


def is_not_modified(if_none_match: str | None, etag: str | None) -> bool:
    if not if_none_match or not etag:
        return False
    tokens = [token.strip() for token in if_none_match.split(",")]
    return "*" in tokens or etag in tokens or f"W/{etag}" in tokens


def _write_atomic(path: Path, data: bytes) -> None:
    """Write one cache file in a single rename with a unique temp name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{path.stem}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def prune_cache(root: Path, max_bytes: int) -> int:
    """Delete oldest cache files until the tree fits ``max_bytes``.

    Returns the number of removed files.  Empty per-gallery directories are
    removed as a side effect so the tree does not grow without bound.
    """
    if max_bytes <= 0:
        return 0
    files: list[tuple[float, int, Path]] = []
    total = 0
    root = Path(root)
    if not root.exists():
        return 0
    for path in root.rglob("*"):
        if not path.is_file() or path.name.endswith(".tmp"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append((stat.st_mtime, stat.st_size, path))
        total += stat.st_size

    removed = 0
    for _mtime, size, path in sorted(files, key=lambda item: item[0]):
        if total <= max_bytes:
            break
        try:
            path.unlink()
        except OSError:
            continue
        total -= size
        removed += 1
        try:
            path.parent.rmdir()
        except OSError:
            pass
    return removed


def _base_url(settings: Any) -> str:
    return str(getattr(settings, "exhentai_base_url", "") or "https://exhentai.org")


def _is_placeholder(url: str) -> bool:
    return urlparse(url).path.rstrip("/").endswith(_LIMIT_SUFFIXES)


def _translate_download_error(exc: Exception) -> OnlineResolveError:
    if isinstance(exc, EhQuotaExceededError):
        return OnlineResolveError(429, "image_limit")
    if isinstance(exc, (EhBannedError, EhAuthRequiredError, EhChallengeError)):
        return OnlineResolveError(503, "upstream")
    message = str(exc).lower()
    if "509" in message or "429" in message or "rate limit" in message:
        return OnlineResolveError(429, "image_limit")
    if "disallowed host" in message or "unexpected host" in message:
        return OnlineResolveError(502, "host_not_allowed")
    return OnlineResolveError(502, "upstream")


async def _download_and_store(
    client_mgr: Any,
    gid: int,
    token: str,
    page: int,
    settings: Any,
) -> Path:
    root = online_cache_dir(settings)
    path = page_cache_path(root, gid, page)
    if path.is_file():
        return path

    # Resolve first: it is self-limited by ``online_reader_concurrency``.
    resolved = await resolve_online_page(client_mgr, gid, token, page)
    image_url = str(resolved.get("url") or "")
    if not image_url:
        raise OnlineResolveError(502, "upstream")
    if _is_placeholder(image_url):
        raise OnlineResolveError(429, "image_limit")
    host = (urlparse(image_url).hostname or "").lower()
    if not _is_allowed_eh_host(host, _base_url(settings)):
        raise OnlineResolveError(502, "host_not_allowed")

    # Download shares the reader limit too, without nesting inside resolve's
    # own acquisition (nested semaphores deadlock when the limit is 1).
    async with _reader_limiter(_reader_limit()):
        try:
            async with client_mgr.client_context() as client:
                data, _content_type = await client.download_image_with_metadata(
                    image_url
                )
        except OnlineResolveError:
            raise
        except (EhClientError, EhClientUnavailableError) as exc:
            raise _translate_download_error(exc) from exc
    if not data:
        raise OnlineResolveError(502, "upstream")

    max_bytes = max(0, int(getattr(settings, "online_cache_max_mb", 512))) * 1024 * 1024
    await asyncio.to_thread(_write_atomic, path, data)
    await asyncio.to_thread(prune_cache, root, max_bytes)
    return path


def _inflight() -> dict[tuple[int, int], asyncio.Task[Path]]:
    bucket = app_state.extra.get(_INFLIGHT)
    if not isinstance(bucket, dict):
        bucket = {}
        app_state.extra[_INFLIGHT] = bucket
    return bucket


async def fetch_online_image(
    client_mgr: Any,
    gid: int,
    token: str,
    page: int,
    settings: Any,
) -> Path:
    """Return the cached image path, fetching it once per ``(gid, page)``.

    Raises :class:`OnlineResolveError` with the same codes the resolve endpoint
    uses, so the router can map failures to one JSON shape.
    """
    gid = int(gid)
    page = int(page)
    root = online_cache_dir(settings)
    path = page_cache_path(root, gid, page)
    if path.is_file():
        return path

    inflight = _inflight()
    key = (gid, page)
    task = inflight.get(key)
    if task is None:
        task = asyncio.ensure_future(
            _download_and_store(client_mgr, gid, token, page, settings)
        )
        inflight[key] = task

        def _cleanup(done: asyncio.Task[Path]) -> None:
            if inflight.get(key) is done:
                inflight.pop(key, None)
            if not done.cancelled():
                # Consume the exception so a cancelled waiter cannot leave an
                # "exception was never retrieved" warning behind.
                done.exception()

        task.add_done_callback(_cleanup)
    return await asyncio.shield(task)
