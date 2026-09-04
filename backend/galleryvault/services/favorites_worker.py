"""Background worker loops and synchronization tasks for favorites and duplicates."""

from __future__ import annotations

import asyncio
import base64
import logging
import time as _time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..app.state import app_state
from ..config import get_settings
from ..db.repository import (
    DownloadRepository,
    FavoritesRepository,
    GalleryRepository,
    GalleryUpdatesRepository,
)
from ..logging import bind_log_context, log_extra
from ..services.tag_translation import translated_tag
from .download_worker import infer_image_quality
from .duplicates import find_duplicate_groups
from .eh_client import EXHENTAI_API_CHUNK_SIZE
from .favorites import FavoritesService
from .storage_usage import storage_tracker

logger = logging.getLogger(__name__)


class FavoritesRepositoryProxy:
    async def _call(self, method: str, *args: Any) -> Any:
        if not app_state.session_factory:
            return None
        async with app_state.session_factory() as session, session.begin():
            return await getattr(FavoritesRepository(session), method)(*args)

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

    async def prune(self, favcat: int, current_gids: set[int]) -> Any:
        return await self._call("prune", favcat, current_gids)

    async def checked(self, favcat: int, success: bool) -> Any:
        return await self._call("checked", favcat, success)

    async def category(self, favcat: int) -> Any:
        return await self._call("category", favcat)


class FavoriteDownloadQueue:
    async def enqueue(
        self, item: Any, mode: str = "favorite", quality: str | None = None
    ) -> bool:
        if not app_state.session_factory:
            return False
        async with app_state.session_factory() as session, session.begin():
            task = await DownloadRepository(session).create(
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
        logger.info("favorite download persisted", extra=log_extra(gid=item.gid, task_id=task.id))
        return True

FAVORITES_SKIP_LIMIT = 5
_FAV_COUNTS_TTL = 300.0
_COVER_SUFFIXES = (".img", ".jpg")
_COVER_HEAL_CHUNK = 25
_fav_counts_cache: dict[str, Any] = {"ts": 0.0, "counts": {}}
_fav_counts_refresh_task: asyncio.Task[None] | None = None
_size_sync_inflight: set[int] = set()


def _unix_to_iso(val: Any) -> str | None:
    if val is None:
        return None
    try:
        ts = float(val)
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def _parse_gdata_tags(tags: list[object] | None) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for tag in tags or []:
        if isinstance(tag, dict):
            ns = str(tag.get("namespace") or "").strip() or "misc"
            name = str(tag.get("name") or "").strip()
            if name:
                parsed.append((ns, name))
        elif isinstance(tag, (list, tuple)) and len(tag) >= 2:
            ns = str(tag[0] or "").strip() or "misc"
            name = str(tag[1] or "").strip()
            if name:
                parsed.append((ns, name))
        elif isinstance(tag, str) and tag.strip():
            if ":" in tag:
                ns, name = tag.split(":", 1)
                parsed.append((ns.strip(), name.strip()))
            else:
                parsed.append(("misc", tag.strip()))
    return parsed


def _tags_to_gdata_strings(raw_tags: list[object] | None) -> list[str]:
    out: list[str] = []
    for tag in raw_tags or []:
        if isinstance(tag, dict):
            ns = str(tag.get("namespace") or "")
            name = str(tag.get("name") or "")
        elif isinstance(tag, (list, tuple)) and len(tag) >= 2:
            ns, name = str(tag[0] or ""), str(tag[1] or "")
        else:
            continue
        name = name.strip()
        if not name:
            continue
        out.append(f"{ns}:{name}" if ns else name)
    return out


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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
    storage_tracker.record_cache_delta(len(raw))


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
    if not pairs or not app_state.session_factory:
        return {}
    gids = [gid for gid, _ in pairs]
    async with app_state.session_factory() as session:
        cached = await GalleryRepository(session).metadata_map(gids)

    missing = [(gid, token) for gid, token in pairs if gid not in cached and token]
    if missing and app_state.eh_client is not None:
        fetched: dict[int, dict[str, Any]] = {}
        for start in range(0, len(missing), batch_size):
            chunk = missing[start : start + batch_size]
            try:
                chunk_meta = await app_state.eh_client.fetch_gmetadata(chunk)
                fetched.update(chunk_meta)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "gdata batch failed during metadata resolution",
                    extra=log_extra(error=type(exc).__name__, count=len(chunk)),
                )
        if fetched:
            try:
                async with app_state.session_factory() as session, session.begin():
                    await GalleryRepository(session).upsert_metadata(
                        [{"gid": gid, **meta} for gid, meta in fetched.items()]
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "failed to persist fetched gdata metadata",
                    extra=log_extra(error=type(exc).__name__),
                )
            cached.update(fetched)
    return cached


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
                raw = await app_state.eh_client.download_image(url)
                if raw:
                    _write_cover_file(_cover_cache_write_path(cache_dir, gid), raw)
                    if encode:
                        uri = _img_data_uri(raw)
                        if uri:
                            result[gid] = uri
            except Exception as exc:  # noqa: BLE001
                logger.debug("cover download failed", extra=log_extra(gid=gid, error=str(exc)))

        await asyncio.gather(*[_fetch(gid, url) for gid, url in need_download])
    return result


def favorites_skip_decision(
    skip_count: int,
    *,
    scheduled: bool,
    category_ready: bool,
    live_count: int,
    known: int,
) -> tuple[bool, int]:
    if not scheduled or not category_ready or live_count <= 0 or known != live_count:
        return False, 0
    next_count = skip_count + 1
    if next_count >= FAVORITES_SKIP_LIMIT:
        return False, 0
    return True, next_count


async def _do_refresh_favorite_counts() -> None:
    if app_state.eh_client is None:
        return
    try:
        async with asyncio.timeout(60):
            counts = await app_state.eh_client.fetch_favorite_counts()
        _fav_counts_cache["ts"] = _time.time()
        _fav_counts_cache["counts"] = counts
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "favorite counts refresh failed", extra=log_extra(error=type(exc).__name__)
        )


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
    if (
        not force
        and isinstance(cached, dict)
        and cached
        and (now - float(_fav_counts_cache.get("ts", 0))) < _FAV_COUNTS_TTL
    ):
        return cached

    if (wait_on_cold and not cached) or force:
        await refresh_favorite_counts()
        fresh = _fav_counts_cache.get("counts")
        if isinstance(fresh, dict) and fresh:
            return fresh
        return cached if isinstance(cached, dict) else {}

    from ..app.dependencies import spawn_task

    spawn_task(refresh_favorite_counts(), "favorite counts warmup")
    return cached if isinstance(cached, dict) else {}


def estimate_cloud_size(cloud_count: int, local_count: int, local_size: int) -> int:
    if not cloud_count:
        return 0
    if not local_count or not local_size:
        return cloud_count * 50 * 1024 * 1024
    return int(cloud_count * (local_size / local_count))


async def favorite_size_sync(favcat: int) -> None:
    if not app_state.session_factory or not app_state.eh_client:
        return
    if favcat in _size_sync_inflight:
        return
    first = not _size_sync_inflight
    _size_sync_inflight.add(favcat)
    tm = app_state.task_manager
    metadata_sync_state = tm.metadata_sync_state if tm else {}
    metadata_sync_state["running"] = True
    metadata_sync_state["stage"] = "listing"
    if first:
        metadata_sync_state["started_at"] = datetime.now(UTC).isoformat()
        metadata_sync_state["applied"] = 0
        metadata_sync_state["last_error"] = None
        metadata_sync_state["history_recorded"] = False
        if tm:
            tm.clear_cancelled("metadata")
    fetched: dict[int, dict[str, Any]] = {}
    try:
        try:
            async with app_state.session_factory() as session, session.begin():
                await GalleryRepository(session).seed_metadata_from_galleries(favcat)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "favorite metadata seed skipped", extra=log_extra(favcat=favcat, error=type(exc).__name__)
            )

        async with app_state.session_factory() as session:
            folder_items = await FavoritesRepository(session).all_gids_for_favcat(favcat)
            folder_gids = [gid for gid, _, _ in folder_items]
            gal_read = GalleryRepository(session)
            cached_meta = await gal_read.metadata_map(folder_gids)
            null_quality = await gal_read.null_image_quality_gids(folder_gids)

        def _positive_eh_size(meta: dict | None) -> bool:
            size = (meta or {}).get("file_size")
            try:
                return int(size) > 0
            except (TypeError, ValueError):
                return False

        missing: list[tuple[int, str]] = []
        seen_need: set[int] = set()
        for gid, token, _thumb in folder_items:
            if not token or gid in seen_need:
                continue
            seen_need.add(gid)
            if gid not in cached_meta or (
                gid in null_quality and not _positive_eh_size(cached_meta.get(gid))
            ):
                missing.append((gid, token))
        metadata_sync_state["total"] = len(missing)
        metadata_sync_state["done"] = 0
        metadata_sync_state["stage"] = "fetching"
        batch_size = EXHENTAI_API_CHUNK_SIZE
        for start in range(0, len(missing), batch_size):
            if tm and tm.is_cancelled("metadata"):
                break
            chunk = missing[start : start + batch_size]
            try:
                chunk_meta = await app_state.eh_client.fetch_gmetadata(chunk)
                fetched.update(chunk_meta)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "gdata batch failed during size sync",
                    extra=log_extra(error=type(exc).__name__, count=len(chunk)),
                )
            metadata_sync_state["done"] = min(len(missing), start + batch_size)
        async with app_state.session_factory() as session, session.begin():
            gal = GalleryRepository(session)
            if fetched:
                await gal.upsert_metadata(
                    [{"gid": gid, **meta} for gid, meta in fetched.items()]
                )
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

        metadata_sync_state["stage"] = "covers"
        cache_dir = _remote_cover_cache_dir()
        coverless: list[tuple[int, str]] = []
        thumb_meta: dict[int, dict[str, Any]] = {}
        for gid, token, listing_thumb in folder_items:
            if _cover_cache_file(cache_dir, gid) is not None:
                continue
            thumb = listing_thumb or (cached_meta.get(gid) or {}).get("thumb")
            if thumb:
                coverless.append((gid, token))
                thumb_meta[gid] = {"thumb": thumb}
        metadata_sync_state["total"] = len(coverless)
        metadata_sync_state["done"] = 0
        for start in range(0, len(coverless), _COVER_HEAL_CHUNK):
            if tm and tm.is_cancelled("metadata"):
                break
            chunk = coverless[start : start + _COVER_HEAL_CHUNK]
            await remote_cover_data_batch(
                chunk,
                {gid: thumb_meta[gid] for gid, _token in chunk},
                download=True,
                encode=False,
            )
            metadata_sync_state["done"] = min(len(coverless), start + _COVER_HEAL_CHUNK)
        if coverless:
            logger.info(
                "favorite covers healed",
                extra=log_extra(favcat=favcat, healed=len(coverless)),
            )

        metadata_sync_state["stage"] = "apply"
        applied = 0
        for _ in range(100):
            if tm and tm.is_cancelled("metadata"):
                break
            async with app_state.session_factory() as session, session.begin():
                applied_round = await GalleryRepository(session).apply_metadata_to_galleries(
                    favcat, 200
                )
            if not applied_round:
                break
            applied += applied_round
            metadata_sync_state["applied"] = (
                int(metadata_sync_state.get("applied") or 0) + applied_round
            )
        if applied:
            logger.info(
                "favorite metadata applied", extra=log_extra(favcat=favcat, applied=applied)
            )
    except Exception as exc:  # noqa: BLE001
        metadata_sync_state["last_error"] = str(exc)
    finally:
        _size_sync_inflight.discard(favcat)
        finishing = not _size_sync_inflight
        if finishing:
            metadata_sync_state["running"] = False
            metadata_sync_state["completed_at"] = datetime.now(UTC).isoformat()
            metadata_sync_state["stage"] = None
            if tm and not metadata_sync_state.get("history_recorded"):
                metadata_sync_state["history_recorded"] = True
                cancelled = tm.is_cancelled("metadata")
                status = (
                    "cancelled"
                    if cancelled
                    else ("failed" if metadata_sync_state.get("last_error") else "success")
                )
                tm.record_task(
                    "metadata",
                    metadata_sync_state.get("started_at"),
                    metadata_sync_state["completed_at"],
                    status,
                    reason=(
                        "cancelled"
                        if cancelled
                        else str(metadata_sync_state.get("last_error") or "")
                    ),
                    done=int(metadata_sync_state.get("done") or 0),
                    total=int(metadata_sync_state.get("total") or 0),
                )
                from ..app.dependencies import spawn_task

                spawn_task(tm.persist_history(), "persist task history")
            if tm:
                tm.clear_cancelled("metadata")


async def run_favorites_check(
    favcat: int, service: FavoritesService, *, scheduled: bool = False
) -> None:
    with bind_log_context(worker="favorites", favcat=favcat):
        await _run_favorites_check_inner(favcat, service, scheduled=scheduled)


async def _run_favorites_check_inner(
    favcat: int, service: FavoritesService, *, scheduled: bool = False
) -> None:
    tm = app_state.task_manager
    favorites_check_state = tm.favorites_check_state if tm else {}
    skip_decision_fn = favorites_skip_decision
    counts_cached_fn = favorite_counts_cached
    session_cm = app_state.session_factory
    if session_cm is None:
        return

    entry: dict[str, Any] = {
        "running": True,
        "started": datetime.now(UTC).isoformat(),
        "error": None,
        "done": 0,
        "total": 0,
    }
    categories = favorites_check_state.setdefault("categories", {})
    already_running = any(
        isinstance(c, dict) and c.get("running") for c in categories.values()
    )
    categories[str(favcat)] = entry
    favorites_check_state["running"] = True
    if not already_running:
        favorites_check_state["started_at"] = datetime.now(UTC).isoformat()
        favorites_check_state["history_recorded"] = False
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

        async with session_cm() as session:
            category = await FavoritesRepository(session).category(favcat)

        live_count = int(entry.get("total") or 0)
        if scheduled and category is not None and getattr(category, "last_success_at", None) is not None:
            try:
                async with session_cm() as session:
                    known = await FavoritesRepository(session).count_known_gids(favcat)
                skip_counts = favorites_check_state.setdefault("skip_counts", {})
                should_skip, next_skip = skip_decision_fn(
                    int(skip_counts.get(str(favcat), 0)),
                    scheduled=True,
                    category_ready=True,
                    live_count=live_count,
                    known=known,
                )
                skip_counts[str(favcat)] = next_skip
                if should_skip:
                    entry["done"] = entry["total"] = live_count
                    entry["skipped"] = True
                    async with session_cm() as session, session.begin():
                        await FavoritesRepository(session).checked(favcat, True)
                    logger.info(
                        "favorites check skipped (cloud count unchanged)",
                        extra=log_extra(favcat=favcat, cloud=live_count, known=known),
                    )
                    return
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "favorites skip heuristic failed",
                    extra=log_extra(favcat=favcat, error=type(exc).__name__),
                )

        def _progress(done: int) -> None:
            entry["done"] = done

        settings = app_state.settings or get_settings()
        # Test stubs (e.g. test_download_cancel_race) may lack archive fields — default safely
        archive_enabled = getattr(settings, "favorites_archive_enabled", False) if settings else False
        archive_max_pages = getattr(settings, "favorites_archive_max_pages", 0) if settings else 0
        archive_quality = getattr(settings, "archive_quality", "resample") if settings else "resample"
        if category is not None and not getattr(category, "enabled", True):
            await service.check_category(favcat, mode="monitor_only", progress=_progress)
        else:
            await service.check_category(
                favcat,
                mode=getattr(category, "mode", "incremental") if category else "incremental",
                progress=_progress,
                archive_enabled=archive_enabled,
                archive_max_pages=archive_max_pages,
                archive_quality=archive_quality,
            )
        entry["error"] = None
        async with session_cm() as session, session.begin():
            await FavoritesRepository(session).checked(favcat, True)
        # Auto-detect gallery updates after a successful favorites check so a
        # re-uploaded gallery (old gid gone, new gid in favorites) does not
        # linger as ``deleted`` or in the wrong category.
        from ..app.dependencies import spawn_task

        spawn_task(favorite_size_sync(favcat), f"favorite size sync {favcat}")
        try:
            from .updates_worker import detect_gallery_updates

            spawn_task(detect_gallery_updates(), "gallery updates detect")
        except Exception as exc:
            logger.debug("ignoring error during post-check updates spawn", exc_info=exc)
    except Exception as exc:  # noqa: BLE001
        entry["error"] = str(exc)
        logger.error(
            "favorites check failed",
            extra=log_extra(favcat=favcat, error=str(exc) or type(exc).__name__),
        )
        try:
            async with session_cm() as session, session.begin():
                await FavoritesRepository(session).checked(favcat, False)
        except Exception as exc2:
            logger.debug("ignoring error during favorites check failure record", exc_info=exc2)
    finally:
        entry["running"] = False
        entry["completed"] = datetime.now(UTC).isoformat()
        all_running = any(
            c.get("running") for c in categories.values() if isinstance(c, dict)
        )
        if not all_running:
            favorites_check_state["running"] = False
            favorites_check_state["completed_at"] = datetime.now(UTC).isoformat()
            if tm and not favorites_check_state.get("history_recorded"):
                favorites_check_state["history_recorded"] = True
                cat_rows = [
                    c for c in categories.values() if isinstance(c, dict)
                ]
                done = sum(int(c.get("done") or 0) for c in cat_rows)
                total = sum(int(c.get("total") or 0) for c in cat_rows)
                failed = any(c.get("error") for c in cat_rows)
                reason = next(
                    (str(c.get("error")) for c in cat_rows if c.get("error")),
                    "",
                )
                tm.record_task(
                    "favorites-check",
                    favorites_check_state.get("started_at"),
                    favorites_check_state["completed_at"],
                    "failed" if failed else "success",
                    reason=reason,
                    done=done,
                    total=total,
                )
                from ..app.dependencies import spawn_task

                spawn_task(tm.persist_history(), "persist task history")


async def favorites_poll_loop(service: FavoritesService | None = None) -> None:
    while True:
        settings = app_state.settings or get_settings()
        # Config stores minutes; poll loop works in seconds — tolerate test stubs
        interval = max(60, int(getattr(settings, "favorites_poll_interval_minutes", 720)) * 60)
        await asyncio.sleep(interval)
        if not settings.exhentai_cookies:
            continue
        if not app_state.session_factory:
            continue
        active_service = service or app_state.favorites_service
        if active_service is None:
            continue
        try:
            async with app_state.session_factory() as session:
                categories = await FavoritesRepository(session).categories()
            for cat in categories:
                if cat.enabled:
                    await run_favorites_check(cat.favcat, active_service, scheduled=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "favorites scheduled poll loop error",
                extra=log_extra(error=type(exc).__name__),
            )


async def run_duplicates_scan() -> None:
    if not app_state.session_factory:
        return
    tm = app_state.task_manager
    duplicates_state = tm.duplicates_state if tm else {}
    duplicates_state.update(
        {"running": True, "stage": "reading", "done": 0, "total": 0, "last_error": None, "groups": []}
    )
    from ..app.dependencies import resolve_display_title
    try:
        async with app_state.session_factory() as session:
            items = await FavoritesRepository(session).all_items()
            gids = list({item[1] for item in items})
            duplicates_state["total"] = len(items)
            duplicates_state["stage"] = "analyzing"
            gallery_titles = await FavoritesRepository(session).gallery_titles_by_gid(gids)
            duplicates_state["done"] = len(items)
            duplicates_state["stage"] = "grouping"
            groups = find_duplicate_groups(items, gallery_titles=gallery_titles)
            group_items = [it for g in groups for it in g["items"]]
            local_ids = [it["gallery_id"] for it in group_items if it["gallery_id"] is not None]
            tag_map = await FavoritesRepository(session).tags_for_gallery_ids(local_ids)
            cloud_pairs = [
                (it["gid"], it["token"]) for it in group_items if it["gallery_id"] is None
            ]
            duplicates_state["stage"] = "enriching"
            gmeta = await favorites_metadata(cloud_pairs) if cloud_pairs else {}
            for it in group_items:
                if it["gallery_id"] is not None:
                    en_title, jp_title = gallery_titles.get(it["gid"], (None, None))
                    it["title_jpn"] = jp_title
                    it["display_title"] = (
                        resolve_display_title(en_title or it.get("title"), jp_title)
                        or it.get("title")
                        or f"gid {it['gid']}"
                    )
                    it["tags"] = [
                        {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
                        for ns, name in tag_map.get(it["gallery_id"], [])
                    ]
                else:
                    meta = gmeta.get(it["gid"], {})
                    it["file_size"] = it["file_size"] or meta.get("file_size")
                    it["title_jpn"] = meta.get("title_jpn")
                    it["display_title"] = (
                        resolve_display_title(it["title"] or meta.get("title"), meta.get("title_jpn"))
                        or it["title"]
                        or f"gid {it['gid']}"
                    )
                    it["posted_at"] = _unix_to_iso(meta.get("posted"))
                    it["tags"] = [
                        {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
                        for ns, name in _parse_gdata_tags(meta.get("tags", []))
                    ]
            cover_map = await remote_cover_data_batch(cloud_pairs, gmeta)
            for it in group_items:
                if it["gallery_id"] is None:
                    it["cover_data"] = cover_map.get(it["gid"])
            missing_posted = [
                (it["gid"], it["token"])
                for it in group_items
                if not it["posted_at"] and it["token"]
            ]
            if missing_posted and app_state.eh_client is not None:
                try:
                    posted_meta = await app_state.eh_client.fetch_gmetadata(missing_posted)
                except Exception as exc:  # noqa: BLE001
                    posted_meta = {}
                    logger.warning(
                        "duplicate posted enrichment failed",
                        extra=log_extra(error=type(exc).__name__),
                    )
                local_write: dict[int, datetime] = {}
                for it in group_items:
                    if it["posted_at"] or it["gid"] not in posted_meta:
                        continue
                    posted = _unix_to_iso(posted_meta[it["gid"]].get("posted"))
                    if not posted:
                        continue
                    it["posted_at"] = posted
                    if it["gallery_id"] is not None:
                        local_write[it["gid"]] = datetime.fromisoformat(posted)
                if local_write:
                    async with app_state.session_factory() as session, session.begin():
                        await FavoritesRepository(session).update_posted_at(local_write)
            ignored_keys = await FavoritesRepository(session).ignored_duplicate_keys()
            groups = [g for g in groups if g["key"] not in ignored_keys]
            groups.sort(key=lambda g: -len(g["items"]))
            duplicates_state["groups"] = groups
            duplicates_state["ignored"] = await FavoritesRepository(session).ignored_duplicates()
            duplicates_state["done"] = len(items)
            duplicates_state["stage"] = "done"
    except Exception as exc:  # noqa: BLE001
        duplicates_state["last_error"] = f"{type(exc).__name__}: {exc}"
        duplicates_state["stage"] = "error"
    finally:
        duplicates_state["running"] = False
