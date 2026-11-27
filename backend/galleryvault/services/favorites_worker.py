"""Background worker loops and synchronization tasks for favorites and duplicates.

The cover-cache, favorite-counts and check/poll clusters now live in the
``galleryvault.services.favorites`` domain package (``cover_cache``, ``counts``,
``poll``), and the duplicates scan lives in
``galleryvault.services.maintain.favorite_duplicates``.  This module stays the
import facade for callers and tests: it keeps the repository proxies, the
download queue, the cloud-size estimate and the favorite size sync, and
re-exports everything that moved so existing imports keep working (CR1).
"""

from __future__ import annotations

import logging
from typing import Any

from ..app.state import app_state
from ..db.repository import (
    DownloadRepository,
    FavoritesRepository,
    GalleryRepository,
    GalleryUpdatesRepository,
)
from ..db.session import safe_transaction
from ..logging import log_extra
from .download_worker import infer_image_quality, notify_new_task
from .eh_client import EXHENTAI_API_CHUNK_SIZE
from .eh_metadata import refresh_gdata
from .favorites import poll as _poll
from .favorites.counts import (
    _fav_counts_cache,
    favorite_counts_cached,
    refresh_favorite_counts,
)
from .favorites.cover_cache import (
    _COVER_HEAL_CHUNK,
    _COVER_SUFFIXES,
    REMOTE_COVER_CONCURRENCY,
    REMOTE_COVER_MIN_INTERVAL,
    REMOTE_COVER_NEG_MAX_ENTRIES,
    REMOTE_COVER_NEG_TTL_MISSING,
    REMOTE_COVER_NEG_TTL_TRANSIENT,
    _cover_cache_file,
    _cover_cache_write_path,
    _cover_clock,
    _cover_failure_ttl,
    _cover_inflight,
    _cover_neg_cache,
    _cover_neg_get,
    _cover_neg_set,
    _fill_remote_cover,
    _get_background_session_factory,
    _img_data_uri,
    _remote_cover_cache_dir,
    _write_cover_file,
    clear_remote_cover_negative,
    ensure_remote_cover,
    favorites_metadata,
    remote_cover_data_batch,
)
from .favorites.poll import (
    FAVORITES_DEFAULT_INTERVAL_MINUTES,
    FAVORITES_FULL_CHECK_MAX_AGE_DAYS,
    FAVORITES_MIN_POLL_INTERVAL_SECONDS,
    FAVORITES_POLL_TICK_SECONDS,
    _favorites_effective_interval_seconds,
    _favorites_fallback_interval_seconds,
    _run_favorites_check_inner,
    _run_favorites_poll_tick,
    favorites_check_due,
    favorites_first_page_all_known,
    favorites_poll_loop,
    favorites_skip_decision,
    full_check_expired,
    run_favorites_check,
)
from .maintain.favorite_duplicates import run_duplicates_scan

__all__ = [
    "FAVORITES_DEFAULT_INTERVAL_MINUTES",
    "FAVORITES_FULL_CHECK_MAX_AGE_DAYS",
    "FAVORITES_MIN_POLL_INTERVAL_SECONDS",
    "FAVORITES_POLL_TICK_SECONDS",
    "REMOTE_COVER_CONCURRENCY",
    "REMOTE_COVER_MIN_INTERVAL",
    "REMOTE_COVER_NEG_MAX_ENTRIES",
    "REMOTE_COVER_NEG_TTL_MISSING",
    "REMOTE_COVER_NEG_TTL_TRANSIENT",
    "_COVER_HEAL_CHUNK",
    "_COVER_SUFFIXES",
    "FavoriteDownloadQueue",
    "FavoritesRepositoryProxy",
    "_cover_cache_file",
    "_cover_cache_write_path",
    "_cover_clock",
    "_cover_failure_ttl",
    "_cover_inflight",
    "_cover_neg_cache",
    "_cover_neg_get",
    "_cover_neg_set",
    "_fav_counts_cache",
    "_favorites_effective_interval_seconds",
    "_favorites_fallback_interval_seconds",
    "_fill_remote_cover",
    "_get_background_session_factory",
    "_img_data_uri",
    "_remote_cover_cache_dir",
    "_run_favorites_check_inner",
    "_run_favorites_poll_tick",
    "_write_cover_file",
    "clear_remote_cover_negative",
    "ensure_remote_cover",
    "estimate_cloud_size",
    "favorite_counts_cached",
    "favorite_size_sync",
    "favorites_check_due",
    "favorites_first_page_all_known",
    "favorites_metadata",
    "favorites_poll_loop",
    "favorites_skip_decision",
    "full_check_expired",
    "refresh_favorite_counts",
    "remote_cover_data_batch",
    "run_duplicates_scan",
    "run_favorites_check",
]

logger = logging.getLogger(__name__)


class FavoritesRepositoryProxy:
    def __init__(self, session: Any = None) -> None:
        self.session = session

    def with_session(self, session: Any) -> FavoritesRepositoryProxy:
        return FavoritesRepositoryProxy(session=session)

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        if self.session is not None:
            return await getattr(FavoritesRepository(self.session), method)(*args, **kwargs)
        session_factory = _get_background_session_factory()
        if not session_factory:
            return None
        async with session_factory() as session, session.begin():
            return await getattr(FavoritesRepository(session), method)(*args, **kwargs)

    async def known_gids(self, favcat: int) -> set[int]:
        res = await self._call("known_gids", favcat)
        return res or set()

    async def existing_gallery_gids(self, gids: list[int]) -> set[int]:
        res = await self._call("existing_gallery_gids", gids)
        return res or set()

    async def remember(self, favcat: int, item: Any) -> Any:
        return await self._call("remember", favcat, item)

    async def remember_many(self, favcat: int, items: list[Any]) -> Any:
        return await self._call("remember_many", favcat, items)

    async def forget(self, favcat: int, gids: list[int]) -> Any:
        return await self._call("forget", favcat, gids)

    async def prune(
        self, favcat: int, current_gids: set[int], allow_empty: bool = False
    ) -> Any:
        return await self._call("prune", favcat, current_gids, allow_empty=allow_empty)

    async def checked(self, favcat: int, success: bool) -> Any:
        return await self._call("checked", favcat, success)

    async def category(self, favcat: int) -> Any:
        return await self._call("category", favcat)


class FavoriteDownloadQueue:
    def __init__(self, session: Any = None) -> None:
        self.session = session

    def with_session(self, session: Any) -> FavoriteDownloadQueue:
        return FavoriteDownloadQueue(session=session)

    async def enqueue(
        self, item: Any, mode: str = "favorite", quality: str | None = None
    ) -> bool:
        if self.session is not None:
            task = await DownloadRepository(self.session, on_new_task=notify_new_task).create(
                item.gid,
                item.token,
                item.title,
                mode,
                quality=quality,
                title_jpn=getattr(item, "title_jpn", None),
            )
            if task is None:
                return False
            await GalleryUpdatesRepository(self.session).attach_download(item.gid, task.id)
            logger.debug("favorite download persisted", extra=log_extra(gid=item.gid, task_id=task.id))
            return True
        session_factory = _get_background_session_factory()
        if not session_factory:
            return False
        async with session_factory() as session, session.begin():
            task = await DownloadRepository(session, on_new_task=notify_new_task).create(
                item.gid,
                item.token,
                item.title,
                mode,
                quality=quality,
                title_jpn=getattr(item, "title_jpn", None),
            )
            if task is None:
                return False
            await GalleryUpdatesRepository(session).attach_download(item.gid, task.id)
        logger.debug("favorite download persisted", extra=log_extra(gid=item.gid, task_id=task.id))
        return True


_size_sync_inflight: set[int] = set()


def estimate_cloud_size(cloud_count: int, local_count: int, local_size: int) -> int:
    if not cloud_count:
        return 0
    if not local_count or not local_size:
        return cloud_count * 50 * 1024 * 1024
    return int(cloud_count * (local_size / local_count))


async def favorite_size_sync(favcat: int) -> None:
    session_factory = _get_background_session_factory()
    if not session_factory or not app_state.eh_client:
        return
    if favcat in _size_sync_inflight:
        return
    from ..app.dependencies import get_task_manager

    tm = get_task_manager()
    fetched: dict[int, dict[str, Any]] = {}
    _size_sync_inflight.add(favcat)
    try:
        async with tm.track_task("metadata", cancellable=True) as tracker:
            tracker.update(stage="listing")
            try:
                async with session_factory() as session, session.begin():
                    await GalleryRepository(session).seed_metadata_from_galleries(favcat)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "favorite metadata seed skipped", extra=log_extra(favcat=favcat, error=type(exc).__name__)
                )

            async with session_factory() as session:
                folder_items = await FavoritesRepository(session).all_gids_for_favcat(favcat)
                folder_gids = [gid for gid, _, _ in folder_items]
                gal_read = GalleryRepository(session)
                cached_meta = await gal_read.metadata_map(folder_gids)
                null_quality = await gal_read.null_image_quality_gids(folder_gids)

            pairs = [(gid, token) for gid, token, _thumb in folder_items if token]
            tracker.update(total=len(pairs), done=0, stage="fetching")
            fetched: dict[int, dict[str, Any]] = {}
            if pairs:
                async with session_factory() as session:
                    if hasattr(session, "scalars"):
                        # refresh_gdata releases the read transaction before the
                        # gdata network call and writes in a short transaction;
                        # an explicit begin() here would keep the connection.
                        fetched = await refresh_gdata(
                            session,
                            pairs,
                            client=app_state.eh_client,
                            batch_size=EXHENTAI_API_CHUNK_SIZE,
                        )
                    elif app_state.eh_client:
                        # Only reached for session doubles without ``scalars``.
                        # Fetch outside any transaction; persist in a short one.
                        gal = GalleryRepository(session)
                        missing = [
                            (gid, token)
                            for gid, token in pairs
                            if gid not in cached_meta
                            or (gid in null_quality and not (cached_meta.get(gid) or {}).get("file_size"))
                        ]
                        for start in range(0, len(missing), EXHENTAI_API_CHUNK_SIZE):
                            chunk = missing[start : start + EXHENTAI_API_CHUNK_SIZE]
                            chunk_meta = await app_state.eh_client.fetch_gmetadata(chunk)
                            fetched.update(chunk_meta)
                        if fetched:
                            async with safe_transaction(session):
                                await gal.upsert_metadata([{"gid": g, **m} for g, m in fetched.items()])
                                refreshed = await gal.metadata_map(list(fetched.keys()))
                                cached_meta.update(refreshed)
            tracker.update(done=len(pairs))

            async with session_factory() as session, session.begin():
                gal = GalleryRepository(session)
                repo = FavoritesRepository(session)
                for gid, meta in fetched.items():
                    size = meta.get("file_size")
                    if size:
                        await repo.set_file_size(favcat, gid, int(size))
                cached_meta.update(fetched)
                combined = dict(cached_meta)
                meta_map = await gal.metadata_map(folder_gids)
                for gid, meta in meta_map.items():
                    if gid not in combined:
                        combined[gid] = meta
                local = await gal.storage_size_map(folder_gids)
                inferred = {
                    gid: quality
                    for gid, (storage_size, stype) in local.items()
                    if (
                        quality := infer_image_quality(
                            storage_size,
                            (combined.get(gid) or {}).get("file_size"),
                            stype,
                        )
                    )
                }
                if inferred:
                    await gal.set_image_qualities(inferred)

            tracker.update(stage="covers")
            cache_dir = _remote_cover_cache_dir()
            coverless: list[tuple[int, str]] = []
            thumb_meta: dict[int, dict[str, Any]] = {}
            for gid, token, listing_thumb in folder_items:
                if _cover_cache_file(cache_dir, gid) is not None:
                    continue
                thumb = listing_thumb or (combined.get(gid) or {}).get("thumb")
                if thumb:
                    coverless.append((gid, token))
                    thumb_meta[gid] = {"thumb": thumb}
                elif token:
                    coverless.append((gid, token))
            tracker.update(total=len(coverless), done=0)
            for start in range(0, len(coverless), _COVER_HEAL_CHUNK):
                if tm.is_cancelled("metadata"):
                    break
                chunk = coverless[start : start + _COVER_HEAL_CHUNK]
                await remote_cover_data_batch(
                    chunk,
                    {gid: thumb_meta[gid] for gid, _token in chunk if gid in thumb_meta},
                    download=True,
                    encode=False,
                )
                for gid, token in chunk:
                    if _cover_cache_file(cache_dir, gid) is None:
                        await ensure_remote_cover(
                            gid, token, cache_dir=cache_dir, cached_meta=combined.get(gid)
                        )
                tracker.update(done=min(len(coverless), start + _COVER_HEAL_CHUNK))
            if coverless:
                logger.info(
                    "favorite covers healed",
                    extra=log_extra(favcat=favcat, healed=len(coverless)),
                )

            tracker.update(stage="apply")
            applied = 0
            for _ in range(100):
                if tm.is_cancelled("metadata"):
                    break
                async with session_factory() as session, session.begin():
                    gal = GalleryRepository(session)
                    if hasattr(gal, "apply_cached_metadata"):
                        applied_round = await gal.apply_cached_metadata(
                            favcat=favcat, limit=200
                        )
                    else:
                        applied_round = await gal.apply_metadata_to_galleries(
                            favcat, 200
                        )
                if not applied_round:
                    break
                applied += applied_round
                tracker.update(applied=int(tracker.get("applied") or 0) + applied_round)
            if applied:
                logger.info(
                    "favorite metadata applied", extra=log_extra(favcat=favcat, applied=applied)
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("favorite size sync error", extra=log_extra(favcat=favcat, error=str(exc)))
    finally:
        _size_sync_inflight.discard(favcat)


# The check flow (poll) spawns the size sync after a successful run; register
# the implementation without poll importing this facade.
_poll.register_size_sync(favorite_size_sync)
