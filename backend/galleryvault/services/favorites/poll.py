"""Favorites check orchestration and the per-folder poll loop.

Owns the scheduled/manual check flow (skip heuristics, progress tracking,
persistence of check timestamps) and the poll tick/loop.  Leaf module of the
favorites domain package: it must not import the legacy
``galleryvault.services.favorites_worker`` facade.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from ...app.state import app_state
from ...config import get_settings
from ...db.repository import FavoritesRepository
from ...logging import bind_log_context, log_extra
from . import counts as favorite_counts
from .cover_cache import _get_background_session_factory

if TYPE_CHECKING:
    from . import FavoritesService

# Same logger name as the legacy module (CR1).
logger = logging.getLogger("galleryvault.services.favorites_worker")

FAVORITES_FULL_CHECK_MAX_AGE_DAYS = 15
# Fixed scheduler heartbeat.  Every tick re-reads the per-folder rows from the
# database, so an interval change takes effect on the next tick instead of
# waiting out the previous global sleep.  Tests patch this constant.
FAVORITES_POLL_TICK_SECONDS = 60
# ExHentai request budget: no folder may be checked more often than once every
# ten minutes, even if the stored/UI value is smaller.  Failures also advance
# ``last_checked_at`` (see ``FavoritesRepository.checked``), so a broken folder
# is retried on this interval rather than on every tick.
FAVORITES_MIN_POLL_INTERVAL_SECONDS = 600
# Used only when a stored interval is missing/invalid.  The legacy global
# ``favorites_poll_interval_minutes`` no longer drives the tick cadence; it is
# kept as a compatibility fallback for rows that never got a per-folder value.
FAVORITES_DEFAULT_INTERVAL_MINUTES = 720

# Late-bound collaborator: the facade owns ``favorite_size_sync`` (it also
# serves the size-sync UI/telegram entry points) and registers it here so the
# check flow can spawn it without poll importing the facade.
_size_sync_runner: Callable[[int], Awaitable[None]] | None = None


def register_size_sync(runner: Callable[[int], Awaitable[None]]) -> None:
    """Register the size-sync coroutine spawned after a successful check."""
    global _size_sync_runner
    _size_sync_runner = runner


def full_check_expired(last_check: datetime | None, *, now: datetime | None = None) -> bool:
    """Whether a full folder listing is due (older than the max age or missing)."""
    if last_check is None:
        return True
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    if last_check.tzinfo is None:
        last_check = last_check.replace(tzinfo=UTC)
    return current - last_check >= timedelta(days=FAVORITES_FULL_CHECK_MAX_AGE_DAYS)


async def favorites_first_page_all_known(favcat: int, known: set[int]) -> bool:
    """Probe page 1 only: every gid there must already be recorded locally.

    A version replacement keeps the cloud count identical but swaps in a gid we
    have never seen, so the count alone is not enough to skip a folder.  Any
    error, empty page or unparseable body is treated as "not proven unchanged"
    and the caller falls back to a full check.
    """
    client = app_state.eh_client
    if client is None:
        return False
    try:
        items = await client.fetch_favorites(favcat, max_pages=1)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "favorites first-page probe failed",
            extra=log_extra(favcat=favcat, error=type(exc).__name__),
        )
        return False
    gids = {int(item.gid) for item in items}
    if not gids:
        logger.warning("favorites first-page probe returned no items", extra=log_extra(favcat=favcat))
        return False
    return gids.issubset(known)


def favorites_skip_decision(
    *,
    scheduled: bool,
    category_ready: bool,
    live_count: int,
    known: int,
    first_page_known: bool,
    last_full_check: datetime | None,
    mode: str = "incremental",
    now: datetime | None = None,
) -> bool:
    if mode == "force":
        # A force folder must re-offer every cloud gid on each check.  Skipping
        # it because the local rows happen to match the live count would hide
        # gids whose earlier enqueue failed and was therefore never recorded.
        return False
    if not scheduled or not category_ready or live_count <= 0 or known != live_count:
        return False
    if not first_page_known:
        return False
    # Persisted deadline replaces the old in-memory "5 consecutive skips"
    # counter, which a container restart (watchtower) reset before it fired.
    return not full_check_expired(last_full_check, now=now)


def _spawn_gallery_updates_detect() -> None:
    from ...app.dependencies import spawn_task

    try:
        from ..updates_worker import detect_gallery_updates

        spawn_task(detect_gallery_updates(), "gallery updates detect")
    except Exception:
        logger.warning("ignoring error during post-check updates spawn", exc_info=True)


async def run_favorites_check(
    favcat: int, service: FavoritesService, *, scheduled: bool = False
) -> None:
    with bind_log_context(worker="favorites", favcat=favcat):
        await _run_favorites_check_inner(favcat, service, scheduled=scheduled)


async def _run_favorites_check_inner(
    favcat: int, service: FavoritesService, *, scheduled: bool = False
) -> None:
    from ...app.dependencies import get_task_manager

    tm = get_task_manager()
    skip_decision_fn = favorites_skip_decision
    counts_cached_fn = favorite_counts.favorite_counts_cached
    session_cm = _get_background_session_factory()
    if session_cm is None:
        return

    entry: dict[str, Any] = {
        "running": True,
        "started": datetime.now(UTC).isoformat(),
        "error": None,
        "done": 0,
        "total": 0,
    }
    async with tm.track_task("favorites-check") as tracker:
        categories = tracker.setdefault("categories", {})
        categories[str(favcat)] = entry
        try:
            try:
                try:
                    counts = await counts_cached_fn(wait_on_cold=True)
                except TypeError:
                    counts = await counts_cached_fn()
                entry["total"] = counts.get(favcat, 0)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "could not fetch live count for check progress",
                    extra=log_extra(favcat=favcat, error=type(exc).__name__),
                )

            live_count = int(entry.get("total") or 0)
            category = None
            known: set[int] = set()
            last_full_check: datetime | None = None
            async with session_cm() as session:
                repo = FavoritesRepository(session)
                category = await repo.category(favcat)
                if (
                    scheduled
                    and category is not None
                    and getattr(category, "last_success_at", None) is not None
                ):
                    try:
                        known = await repo.known_gids(favcat)
                        last_full_check = (await repo.full_check_times()).get(favcat)
                    except Exception as exc:  # noqa: BLE001
                        # Unknown local state must never authorise a skip.
                        known = set()
                        last_full_check = None
                        logger.warning(
                            "favorites skip heuristic failed",
                            extra=log_extra(favcat=favcat, error=type(exc).__name__),
                        )

            if category is None:
                category_mode = "incremental"
            elif not getattr(category, "enabled", True):
                category_mode = "monitor_only"
            else:
                category_mode = getattr(category, "mode", "incremental") or "incremental"

            if (
                scheduled
                and category is not None
                and getattr(category, "last_success_at", None) is not None
                and category_mode != "force"
                and live_count > 0
                and len(known) == live_count
                and not full_check_expired(last_full_check)
            ):
                try:
                    first_page_known = await favorites_first_page_all_known(favcat, known)
                    should_skip = skip_decision_fn(
                        scheduled=True,
                        category_ready=True,
                        live_count=live_count,
                        known=len(known),
                        first_page_known=first_page_known,
                        last_full_check=last_full_check,
                        mode=category_mode,
                    )
                except Exception as exc:  # noqa: BLE001
                    should_skip = False
                    logger.warning(
                        "favorites skip heuristic failed",
                        extra=log_extra(favcat=favcat, error=type(exc).__name__),
                    )
                if should_skip:
                    entry["done"] = entry["total"] = live_count
                    entry["skipped"] = True
                    # Fresh session: the read session above has left its
                    # autobegun transaction, and a nested begin() would raise.
                    async with session_cm() as session, session.begin():
                        await FavoritesRepository(session).checked(favcat, True)
                    logger.info(
                        "favorites check skipped (count unchanged and first page known)",
                        extra=log_extra(favcat=favcat, cloud=live_count, known=len(known)),
                    )
                    # Cheap DB-only pass; it has its own "detecting" guard.
                    _spawn_gallery_updates_detect()
                    return

            def _progress(done: int) -> None:
                entry["done"] = done

            settings = app_state.settings or get_settings()
            archive_enabled = getattr(settings, "favorites_archive_enabled", False) if settings else False
            archive_max_pages = getattr(settings, "favorites_archive_max_pages", 0) if settings else 0
            archive_quality = getattr(settings, "archive_quality", "resample") if settings else "resample"
            check_kwargs: dict[str, Any] = {
                "progress": _progress,
            }
            if category_mode == "monitor_only":
                check_kwargs["mode"] = "monitor_only"
            else:
                check_kwargs["mode"] = category_mode
                check_kwargs["archive_enabled"] = archive_enabled
                check_kwargs["archive_max_pages"] = archive_max_pages
                check_kwargs["archive_quality"] = archive_quality

            result = await service.check_category(favcat, **check_kwargs)
            failed = int(getattr(result, "failed", 0) or 0)
            if failed > 0:
                # Keep the failure visible: a failed enqueue must not be
                # reported as a successful check, and the full-check deadline
                # must not move so the next poll retries the missing gids.
                entry["error"] = f"{failed} favorite download(s) failed to enqueue"
                tracker.update(last_error=entry["error"])
                logger.warning(
                    "favorites check finished with enqueue failures",
                    extra=log_extra(favcat=favcat, failed=failed),
                )
                async with session_cm() as session, session.begin():
                    await FavoritesRepository(session).checked(favcat, False)
            else:
                entry["error"] = None
                async with session_cm() as session, session.begin():
                    await FavoritesRepository(session).checked(favcat, True)
                # Only a successful full listing refreshes the deadline; skipped
                # runs must not extend it.  A failed write is logged, not retried as
                # a failed check (the listing itself succeeded).
                try:
                    async with session_cm() as session, session.begin():
                        await FavoritesRepository(session).set_full_check_time(favcat)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "could not persist favorites full-check timestamp",
                        extra=log_extra(favcat=favcat, error=type(exc).__name__),
                    )

            from ...app.dependencies import spawn_task

            if _size_sync_runner is not None:
                spawn_task(_size_sync_runner(favcat), f"favorite size sync {favcat}")
            _spawn_gallery_updates_detect()
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)
            tracker.update(last_error=str(exc))
            logger.error(
                "favorites check failed",
                extra=log_extra(favcat=favcat, error=str(exc) or type(exc).__name__),
            )
            try:
                async with session_cm() as session, session.begin():
                    await FavoritesRepository(session).checked(favcat, False)
            except Exception:
                logger.warning("ignoring error during favorites check failure record", exc_info=True)
        finally:
            entry["running"] = False
            entry["completed"] = datetime.now(UTC).isoformat()


def _favorites_fallback_interval_seconds(settings: Any) -> int:
    raw = getattr(settings, "favorites_poll_interval_minutes", FAVORITES_DEFAULT_INTERVAL_MINUTES)
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        minutes = FAVORITES_DEFAULT_INTERVAL_MINUTES
    return max(FAVORITES_MIN_POLL_INTERVAL_SECONDS, minutes * 60)


def _favorites_effective_interval_seconds(category: Any, fallback_seconds: int) -> int:
    """Return the clamped per-folder interval (seconds)."""
    raw = getattr(category, "poll_interval_seconds", None)
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        seconds = fallback_seconds
    return max(FAVORITES_MIN_POLL_INTERVAL_SECONDS, seconds)


def favorites_check_due(category: Any, now: datetime, fallback_seconds: int) -> bool:
    """Whether ``category`` is due, based on its own interval and last check.

    A missing ``last_checked_at`` counts as due (first run / new folder).
    ``last_checked_at`` is written for failed checks too, so errors do not
    retry on every tick.
    """
    last_checked = getattr(category, "last_checked_at", None)
    if last_checked is None:
        return True
    if last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=UTC)
    interval = _favorites_effective_interval_seconds(category, fallback_seconds)
    return (now - last_checked).total_seconds() >= interval


async def _run_favorites_poll_tick(
    settings: Any,
    service: FavoritesService,
    session_factory: Any,
    *,
    now: datetime | None = None,
) -> None:
    """One scheduler tick: check only the folders whose own interval elapsed."""
    async with session_factory() as session:
        categories = await FavoritesRepository(session).categories()
    fallback_seconds = _favorites_fallback_interval_seconds(settings)
    current = now or datetime.now(UTC)
    for cat in categories:
        if not getattr(cat, "enabled", False):
            continue
        if not favorites_check_due(cat, current, fallback_seconds):
            continue
        await run_favorites_check(cat.favcat, service, scheduled=True)


async def favorites_poll_loop(service: FavoritesService | None = None) -> None:
    while True:
        # Sleep for a fixed tick, then re-read settings and folder rows.  The
        # per-folder interval is evaluated inside the tick; the legacy global
        # interval is only a fallback for invalid rows.
        await asyncio.sleep(FAVORITES_POLL_TICK_SECONDS)
        settings = app_state.settings or get_settings()
        if not settings.exhentai_cookies:
            continue
        session_factory = _get_background_session_factory()
        if not session_factory:
            continue
        active_service = service or app_state.favorites_service
        if active_service is None:
            continue
        try:
            await _run_favorites_poll_tick(settings, active_service, session_factory)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "favorites scheduled poll loop error",
                extra=log_extra(error=type(exc).__name__),
            )
