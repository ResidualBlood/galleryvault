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
from ..db.repository import DownloadRepository, FavoritesRepository, GalleryRepository
from ..logging import bind_log_context, log_extra
from ..services.tag_translation import translated_tag
from .duplicates import find_duplicate_groups
from .eh_client import EXHENTAI_API_CHUNK_SIZE
from .favorites import FavoritesService

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
                item.gid, item.token, item.title, mode, quality=quality
            )
            if task is None:
                return False
        logger.info("favorite download persisted", extra=log_extra(gid=item.gid, task_id=task.id))
        return True

FAVORITES_SKIP_LIMIT = 5
_FAV_COUNTS_TTL = 300.0
_fav_counts_cache: dict[str, Any] = {"ts": 0.0, "counts": {}}
_fav_counts_refreshing = False


def _unix_to_iso(val: Any) -> str | None:
    if val is None:
        return None
    try:
        ts = float(val)
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def _parse_gdata_tags(tags: list[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for tag in tags:
        if ":" in tag:
            ns, name = tag.split(":", 1)
            parsed.append((ns.strip(), name.strip()))
        else:
            parsed.append(("misc", tag.strip()))
    return parsed


def _remote_cover_cache_dir() -> Path:
    settings = app_state.settings or get_settings()
    d = Path(settings.thumbnail_cache_dir).parent / "remote-covers"
    d.mkdir(parents=True, exist_ok=True)
    return d


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
) -> dict[int, str]:
    if not pairs:
        return {}
    if metadata is None:
        metadata = await favorites_metadata(pairs)
    cache_dir = _remote_cover_cache_dir()
    result: dict[int, str] = {}
    need_download: list[tuple[int, str]] = []
    for gid, _ in pairs:
        thumb_url = (metadata.get(gid) or {}).get("thumb")
        if not thumb_url:
            continue
        cached_file = cache_dir / f"{gid}.jpg"
        if cached_file.exists():
            try:
                uri = _img_data_uri(cached_file.read_bytes())
                if uri:
                    result[gid] = uri
                continue
            except OSError:
                pass
        need_download.append((gid, thumb_url))

    if need_download and app_state.eh_client is not None:
        # Rely on EhClient's own image/page semaphores — no extra local limiter
        # to avoid double throttling (previous Semaphore(6) stacked with client's 12).

        async def _fetch(gid: int, url: str) -> None:
            try:
                assert app_state.eh_client is not None
                raw = await app_state.eh_client.download_image(url)
                if raw:
                    cached_file = cache_dir / f"{gid}.jpg"
                    cached_file.write_bytes(raw)
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


async def refresh_favorite_counts() -> None:
    global _fav_counts_refreshing
    if _fav_counts_refreshing or app_state.eh_client is None:
        return
    _fav_counts_refreshing = True
    try:
        async with asyncio.timeout(60):
            counts = await app_state.eh_client.fetch_favorite_counts()
        _fav_counts_cache["ts"] = _time.time()
        _fav_counts_cache["counts"] = counts
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "favorite counts refresh failed", extra=log_extra(error=type(exc).__name__)
        )
    finally:
        _fav_counts_refreshing = False


async def favorite_counts_cached() -> dict[int, int]:
    now = _time.time()
    cached = _fav_counts_cache.get("counts")
    if (
        isinstance(cached, dict)
        and cached
        and (now - float(_fav_counts_cache.get("ts", 0))) < _FAV_COUNTS_TTL
    ):
        return cached
    from ..app import main
    spawn_fn = getattr(main, "_spawn", None)
    if spawn_fn is not None:
        spawn_fn(refresh_favorite_counts(), "favorite counts warmup")
    else:
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
    tm = app_state.task_manager
    metadata_sync_state = tm.metadata_sync_state if tm else {}
    if metadata_sync_state.get("running"):
        return
    metadata_sync_state["running"] = True
    metadata_sync_state["stage"] = "listing"
    metadata_sync_state["started_at"] = datetime.now(UTC).isoformat()
    if tm:
        tm.clear_cancelled("metadata")
    try:
        async with app_state.session_factory() as session:
            gids = await FavoritesRepository(session).gids_for_favcat(favcat)
            cached_meta = await GalleryRepository(session).metadata_map(gids)
            missing = [(gid, "") for gid in gids if gid not in cached_meta]

        metadata_sync_state["total"] = len(missing)
        metadata_sync_state["done"] = 0
        metadata_sync_state["stage"] = "fetching"

        batch_size = EXHENTAI_API_CHUNK_SIZE
        fetched: dict[int, dict[str, Any]] = {}
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

        if fetched:
            async with app_state.session_factory() as session, session.begin():
                await GalleryRepository(session).upsert_metadata(
                    [{"gid": gid, **meta} for gid, meta in fetched.items()]
                )
    except Exception as exc:  # noqa: BLE001
        metadata_sync_state["last_error"] = str(exc)
    finally:
        metadata_sync_state["running"] = False
        metadata_sync_state["completed_at"] = datetime.now(UTC).isoformat()
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
    from ..app import main
    tm = app_state.task_manager
    favorites_check_state = getattr(main, "favorites_check_state", None)
    if favorites_check_state is None:
        favorites_check_state = tm.favorites_check_state if tm else {}
    skip_decision_fn = getattr(main, "_favorites_skip_decision", favorites_skip_decision)
    counts_cached_fn = getattr(main, "_favorite_counts_cached", favorite_counts_cached)
    session_cm = getattr(main, "_settings_session", None) or (app_state.session_factory if app_state else None)
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
    categories[str(favcat)] = entry
    favorites_check_state["running"] = True
    if favorites_check_state.get("started_at") is None:
        favorites_check_state["started_at"] = datetime.now(UTC).isoformat()
        favorites_check_state["history_recorded"] = False
    try:
        try:
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

        # Use main._settings() (which adopts monkeypatched app.state) when available,
        # so tests that stub main.app.state.settings do not leave app_state.settings stale.
        settings = None
        try:
            from ..app.main import _settings as _main_settings  # local import to avoid cycle

            settings = _main_settings()
        except Exception:  # noqa: BLE001
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
        try:
            from ..app.dependencies import spawn_task
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
                await FavoritesRepository(session).checked(favcat, False, str(exc))
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
                tm.record_task(
                    "favorites-check",
                    favorites_check_state.get("started_at"),
                    favorites_check_state["completed_at"],
                    "success" if not entry.get("error") else "failed",
                    reason=entry.get("error") or "",
                    done=entry.get("done", 0),
                    total=entry.get("total", 0),
                )
                from ..app.dependencies import spawn_task

                spawn_task(tm.persist_history(), "persist task history")


async def favorites_poll_loop(service: FavoritesService | None = None) -> None:
    while True:
        try:
            from ..app.main import _settings as _main_settings

            settings = _main_settings()
        except Exception:  # noqa: BLE001
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
