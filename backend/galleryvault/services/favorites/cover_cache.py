"""Remote cover cache: negative cache, single-flight fill and batch healing.

The module owns the process-local cover throttle (semaphore/spacing), the
per-gid negative cache and the on-disk ``remote-covers`` cache.  It is a leaf
of the favorites domain package: it must not import the legacy
``galleryvault.services.favorites_worker`` facade.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time as _time
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ...app.state import app_state
from ...config import get_settings
from ...db.models import FavoriteItem, Gallery, GalleryMetadata
from ...fsutil import write_atomic
from ...logging import log_extra
from ..eh_client import (
    EXHENTAI_API_CHUNK_SIZE,
    EhAuthRequiredError,
    EhBannedError,
    EhChallengeError,
    EhImageSlowError,
    EhQuotaExceededError,
)
from ..eh_metadata import refresh_gdata
from ..storage_usage import storage_tracker

# Same logger name as the legacy module: log records keep their historic
# ``galleryvault.services.favorites_worker`` origin (CR1).
logger = logging.getLogger("galleryvault.services.favorites_worker")

_COVER_SUFFIXES = (".img", ".jpg")
_COVER_HEAL_CHUNK = 25
# Remote cover fetches are the one EH path that fans out per gallery. During an
# anti-bot challenge every retry re-hits upstream, so cap the fan-out, keep
# consecutive cover requests apart, and remember recent failures per gid.
REMOTE_COVER_CONCURRENCY = 2
REMOTE_COVER_MIN_INTERVAL = 1.0
# A gid that produced nothing upstream (no thumb / unexpected failure) is
# unlikely to change soon; a challenge/auth/network failure may clear quickly.
REMOTE_COVER_NEG_TTL_MISSING = 6 * 3600.0
REMOTE_COVER_NEG_TTL_TRANSIENT = 30 * 60.0
REMOTE_COVER_NEG_MAX_ENTRIES = 4096
_cover_neg_cache: OrderedDict[int, float] = OrderedDict()
_cover_inflight: dict[int, asyncio.Task[Path | None]] = {}
_cover_gate: asyncio.Semaphore | None = None
_cover_gate_loop: asyncio.AbstractEventLoop | None = None
_cover_next_slot = 0.0


def _get_background_session_factory() -> Any:
    return getattr(app_state, "background_session_factory", None) or app_state.session_factory


def _cover_clock() -> float:
    """Monotonic clock for the cover negative cache (patched in tests)."""
    return _time.monotonic()


def _remote_cover_gate() -> asyncio.Semaphore:
    """Return the process-wide upstream cover semaphore for the running loop."""
    global _cover_gate, _cover_gate_loop
    try:
        loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - only outside an event loop
        loop = None
    if _cover_gate is None or _cover_gate_loop is not loop:
        _cover_gate = asyncio.Semaphore(REMOTE_COVER_CONCURRENCY)
        _cover_gate_loop = loop
    return _cover_gate


@asynccontextmanager
async def _remote_cover_slot() -> AsyncIterator[None]:
    """Hold one upstream cover slot, spacing consecutive requests apart."""
    global _cover_next_slot
    async with _remote_cover_gate():
        wait = _cover_next_slot - _time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _cover_next_slot = _time.monotonic() + REMOTE_COVER_MIN_INTERVAL
        yield


def _cover_neg_get(gid: int) -> bool:
    gid = int(gid)
    expires_at = _cover_neg_cache.get(gid)
    if expires_at is None:
        return False
    if expires_at <= _cover_clock():
        _cover_neg_cache.pop(gid, None)
        return False
    _cover_neg_cache.move_to_end(gid)
    return True


def _cover_neg_set(gid: int, ttl: float) -> None:
    gid = int(gid)
    _cover_neg_cache[gid] = _cover_clock() + max(ttl, 0.0)
    _cover_neg_cache.move_to_end(gid)
    while len(_cover_neg_cache) > REMOTE_COVER_NEG_MAX_ENTRIES:
        _cover_neg_cache.popitem(last=False)


def clear_remote_cover_negative(gid: int | None = None) -> None:
    """Forget cached cover failures.

    Called on a successful fetch; explicit "re-fetch cover / refresh metadata"
    entry points should call this too (``gid=None`` clears every entry) so a
    user-triggered retry is never blocked by the negative cache.
    """
    if gid is None:
        _cover_neg_cache.clear()
    else:
        _cover_neg_cache.pop(int(gid), None)


def _cover_failure_ttl(exc: BaseException | None) -> float:
    """Classify a failed cover fill: transient upstream errors retry soon."""
    if exc is None:
        return REMOTE_COVER_NEG_TTL_MISSING
    if isinstance(
        exc,
        (
            EhChallengeError,
            EhAuthRequiredError,
            EhBannedError,
            EhImageSlowError,
            EhQuotaExceededError,
            httpx.HTTPError,
            OSError,
            TimeoutError,
        ),
    ):
        return REMOTE_COVER_NEG_TTL_TRANSIENT
    return REMOTE_COVER_NEG_TTL_MISSING


def _remote_cover_cache_dir() -> Path:
    settings = app_state.settings or get_settings()
    d = Path(settings.thumbnail_cache_dir).parent / "remote-covers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cover_cache_file(cache_dir: Path, gid: int) -> Path | None:
    for suffix in _COVER_SUFFIXES:
        path = cache_dir / f"{int(gid)}{suffix}"
        if path.is_file():
            return path
    return None


def _cover_cache_write_path(cache_dir: Path, gid: int) -> Path:
    return cache_dir / f"{int(gid)}.img"


def _write_cover_file(path: Path, raw: bytes) -> None:
    """Write a cover image in one rename, with a per-call unique temp file.

    Two concurrent cache fillers for the same gid must not share a temp path:
    the loser would then ``replace()`` a file the winner already moved away.
    """
    write_atomic(path, raw, tmp_prefix=f"{path.name}.")
    storage_tracker.record_cache_delta(len(raw))


async def ensure_remote_cover(
    gid: int,
    token: str | None = None,
    cache_dir: Path | None = None,
    source: str = "thumb0",
    *,
    cached_meta: dict[str, Any] | None = None,
) -> Path | None:
    """Return the cached cover for ``gid``, filling it at most once per gid.

    Misses are negative-cached (so a burst of callers cannot re-hit EH) and
    coalesced into a single upstream flow per gid.
    """
    cache_dir = cache_dir or _remote_cover_cache_dir()
    cached = _cover_cache_file(cache_dir, gid)
    if cached is not None:
        return cached

    if _cover_neg_get(gid):
        logger.debug(
            "remote cover negative cache hit: gid=%s source=%s event=neg_hit",
            gid,
            source,
            extra=log_extra(gid=int(gid), source=source, event="neg_hit"),
        )
        return None

    key = int(gid)
    pending = _cover_inflight.get(key)
    if pending is None:
        pending = asyncio.ensure_future(
            _fill_remote_cover(key, token, cache_dir, source, cached_meta)
        )
        _cover_inflight[key] = pending

        def _drop(task: asyncio.Task[Path | None], key: int = key) -> None:
            if _cover_inflight.get(key) is task:
                _cover_inflight.pop(key, None)

        pending.add_done_callback(_drop)

    try:
        return await asyncio.shield(pending)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - the fill records its own failure
        return None


async def _fill_remote_cover(
    gid: int,
    token: str | None,
    cache_dir: Path,
    source: str,
    cached_meta: dict[str, Any] | None,
) -> Path | None:
    logger.info(
        "cover miss: gid=%s source=%s event=miss",
        gid,
        source,
        extra=log_extra(gid=int(gid), source=source, event="miss"),
    )

    client = app_state.eh_client
    if client is None:
        return None

    last_error: BaseException | None = None
    thumb_url: str | None = None
    has_cached_meta = False
    if cached_meta is not None:
        thumb_url = cached_meta.get("thumb") or None
        has_cached_meta = True

    session_factory = _get_background_session_factory()
    if not thumb_url and not has_cached_meta and session_factory:
        try:
            async with session_factory() as session:
                if hasattr(session, "scalar"):
                    thumb_url = await session.scalar(
                        select(FavoriteItem.thumb).where(
                            FavoriteItem.gid == int(gid),
                            FavoriteItem.thumb.is_not(None),
                        ).limit(1)
                    )
                    if not thumb_url:
                        thumb_url = await session.scalar(
                            select(GalleryMetadata.thumb).where(
                                GalleryMetadata.gid == int(gid),
                                GalleryMetadata.thumb.is_not(None),
                            ).limit(1)
                        )
                    if not thumb_url:
                        source_meta = await session.scalar(
                            select(Gallery.source_meta).where(
                                Gallery.gid == int(gid),
                                Gallery.source_meta.is_not(None),
                            ).limit(1)
                        )
                        if isinstance(source_meta, dict) and source_meta.get("thumb"):
                            thumb_url = str(source_meta["thumb"])
                    if not thumb_url:
                        has_cached_meta = bool(
                            await session.scalar(
                                select(GalleryMetadata.gid).where(
                                    GalleryMetadata.gid == int(gid),
                                ).limit(1)
                            )
                        )
        except (SQLAlchemyError, Exception):  # noqa: BLE001
            thumb_url = None

    if not token and session_factory:
        try:
            async with session_factory() as session:
                if hasattr(session, "scalar"):
                    token = await session.scalar(
                        select(Gallery.token).where(
                            Gallery.gid == int(gid),
                            Gallery.token.is_not(None),
                        ).limit(1)
                    )
                    if not token:
                        token = await session.scalar(
                            select(FavoriteItem.token).where(
                                FavoriteItem.gid == int(gid),
                                FavoriteItem.token.is_not(None),
                            ).limit(1)
                        )
                    if not token:
                        token = await session.scalar(
                            select(GalleryMetadata.token).where(
                                GalleryMetadata.gid == int(gid),
                                GalleryMetadata.token.is_not(None),
                            ).limit(1)
                        )
        except (SQLAlchemyError, Exception):  # noqa: BLE001, S110
            pass

    if not thumb_url and not has_cached_meta and token and hasattr(client, "fetch_gmetadata"):
        try:
            chunk_meta = None
            if session_factory:
                try:
                    async with session_factory() as session:
                        if hasattr(session, "scalars"):
                            # No explicit transaction: refresh_gdata releases
                            # the read transaction before the gdata network
                            # call and persists in a fresh short one.
                            chunk_meta = await refresh_gdata(
                                session, [(int(gid), token)], client=client
                            )
                except (SQLAlchemyError, Exception):  # noqa: BLE001
                    chunk_meta = None
            meta = (chunk_meta or {}).get(int(gid)) or {}
            thumb_url = meta.get("thumb") or None
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            thumb_url = None

    data: bytes | None = None
    if thumb_url:
        try:
            async with _remote_cover_slot():
                data = await client.download_image(str(thumb_url))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            data = None

    if data is None and token:
        try:
            async with _remote_cover_slot():
                res = await client.fetch_gallery_cover(int(gid), token)
            if isinstance(res, tuple) and res:
                data = res[0]
            elif isinstance(res, (bytes, bytearray)):
                data = bytes(res)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            data = None

    if data:
        write_path = _cover_cache_write_path(cache_dir, gid)
        _write_cover_file(write_path, data)
        clear_remote_cover_negative(gid)
        return write_path

    # Remember the miss so retries within the TTL do not hit upstream again.
    _cover_neg_set(gid, _cover_failure_ttl(last_error))
    return None


def _img_data_uri(raw: bytes) -> str | None:
    if not raw:
        return None
    if raw.startswith(b"\x89PNG"):
        mime = "image/png"
    elif raw.startswith((b"\xff\xd8\xff", b"\xff\xd8")):
        mime = "image/jpeg"
    elif raw.startswith(b"GIF8"):
        mime = "image/gif"
    elif raw.startswith(b"RIFF") and b"WEBP" in raw[:12]:
        mime = "image/webp"
    else:
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


async def favorites_metadata(
    pairs: list[tuple[int, str]], batch_size: int = EXHENTAI_API_CHUNK_SIZE
) -> dict[int, dict[str, Any]]:
    if not pairs:
        return {}
    session_factory = _get_background_session_factory()
    if session_factory:
        # The caller owns no transaction here: refresh_gdata releases the
        # connection before the network and writes in a short transaction.
        async with session_factory() as session:
            return await refresh_gdata(
                session, pairs, client=app_state.eh_client, batch_size=batch_size
            )
    if app_state.eh_client:
        return await app_state.eh_client.fetch_gmetadata(pairs)
    return {}


async def remote_cover_data_batch(
    pairs: list[tuple[int, str]],
    metadata: dict[int, dict[str, Any]] | None = None,
    *,
    download: bool = True,
    encode: bool = True,
) -> dict[int, str]:
    if not pairs:
        return {}
    if metadata is None and (download or encode):
        metadata = await favorites_metadata(pairs)
    metadata = metadata or {}
    cache_dir = _remote_cover_cache_dir()
    result: dict[int, str] = {}
    need_download: list[tuple[int, str]] = []
    for gid, _ in pairs:
        cached_file = _cover_cache_file(cache_dir, gid)
        if cached_file is not None:
            if encode:
                try:
                    uri = _img_data_uri(cached_file.read_bytes())
                    if uri:
                        result[gid] = uri
                except OSError:
                    pass
            continue
        thumb_url = str((metadata.get(gid) or {}).get("thumb") or "")
        if download and thumb_url:
            need_download.append((gid, thumb_url))

    if need_download and app_state.eh_client is not None:
        async def _fetch(gid: int, url: str) -> None:
            try:
                assert app_state.eh_client is not None
                # Same global gate as ensure_remote_cover: the heal loop must not
                # burst past the upstream cover concurrency/spacing limits.
                async with _remote_cover_slot():
                    raw = await app_state.eh_client.download_image(url)
                if raw:
                    _write_cover_file(_cover_cache_write_path(cache_dir, gid), raw)
                    clear_remote_cover_negative(gid)
                    if encode:
                        uri = _img_data_uri(raw)
                        if uri:
                            result[gid] = uri
            except Exception as exc:  # noqa: BLE001
                _cover_neg_set(gid, _cover_failure_ttl(exc))
                logger.debug("cover download failed", extra=log_extra(gid=gid, error=str(exc)))

        # Bound the fan-out: a folder can miss thousands of covers, and an
        # unbounded gather would queue every download at once (memory + slow
        # cancellation) instead of feeding the shared image semaphore steadily.
        for start in range(0, len(need_download), _COVER_HEAL_CHUNK):
            chunk = need_download[start : start + _COVER_HEAL_CHUNK]
            await asyncio.gather(*[_fetch(gid, url) for gid, url in chunk])
    return result
