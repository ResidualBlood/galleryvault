"""Cached ExHentai favorite-folder counts.

The counts feed the check/skip heuristics; they are cached briefly (a parsed
mapping for its TTL, an unconfirmed ``None`` for a shorter one) so a broken
header or a cold cache does not make every caller request the favorites page.
Leaf module of the favorites domain package: it must not import the legacy
``galleryvault.services.favorites_worker`` facade.
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from typing import Any

from ...app.state import app_state
from ...logging import log_extra

# Same logger name as the legacy module (CR1).
logger = logging.getLogger("galleryvault.services.favorites_worker")

_FAV_COUNTS_TTL = 300.0
_FAV_COUNTS_EMPTY_TTL = 60.0
_fav_counts_cache: dict[str, Any] = {"ts": 0.0, "counts": None}
_fav_counts_refresh_task: asyncio.Task[None] | None = None


async def _do_refresh_favorite_counts() -> None:
    if app_state.eh_client is None:
        return
    try:
        async with asyncio.timeout(60):
            counts = await app_state.eh_client.fetch_favorite_counts()
        if not counts:
            # ``None``/empty means "could not confirm" (login wall, redirect or
            # markup drift), never "the folder has zero items" — a confirmed
            # zero arrives as ``{favcat: 0}``.
            logger.warning("favorite counts unavailable (page header not parsed)")
        _fav_counts_cache["ts"] = _time.time()
        _fav_counts_cache["counts"] = counts or None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "favorite counts refresh failed", extra=log_extra(error=type(exc).__name__)
        )
        # Cache the failure briefly (unknown, not zero) so a cold/expired cache
        # does not make every caller re-request the favorites page. A previously
        # parsed mapping is kept for its normal TTL.
        if not isinstance(_fav_counts_cache.get("counts"), dict):
            _fav_counts_cache["ts"] = _time.time()
            _fav_counts_cache["counts"] = None


def _clear_refresh_task(task: asyncio.Task[None]) -> None:
    global _fav_counts_refresh_task
    if _fav_counts_refresh_task is task:
        _fav_counts_refresh_task = None


async def refresh_favorite_counts() -> None:
    global _fav_counts_refresh_task
    if _fav_counts_refresh_task is not None and not _fav_counts_refresh_task.done():
        await asyncio.shield(_fav_counts_refresh_task)
        return
    task = asyncio.create_task(_do_refresh_favorite_counts())
    task.add_done_callback(_clear_refresh_task)
    _fav_counts_refresh_task = task
    await asyncio.shield(task)


async def favorite_counts_cached(wait_on_cold: bool = False, force: bool = False) -> dict[int, int]:
    now = _time.time()
    cached = _fav_counts_cache.get("counts")
    if "counts" in _fav_counts_cache:
        # A parsed mapping is a result (including ``{favcat: 0}``); ``None`` is
        # "could not confirm" and is retried sooner, but still cached briefly so
        # a broken header does not make every caller hit the favorites page.
        ttl = _FAV_COUNTS_TTL if cached else _FAV_COUNTS_EMPTY_TTL
        if not force and (now - float(_fav_counts_cache.get("ts", 0))) < ttl:
            return cached if isinstance(cached, dict) else {}

    if (wait_on_cold and not cached) or force:
        await refresh_favorite_counts()
        fresh = _fav_counts_cache.get("counts")
        if isinstance(fresh, dict) and fresh:
            return fresh
        return cached if isinstance(cached, dict) else {}

    from ...app.dependencies import spawn_task

    spawn_task(refresh_favorite_counts(), "favorite counts warmup")
    return cached if isinstance(cached, dict) else {}
