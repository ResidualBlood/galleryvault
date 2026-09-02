"""Favorites endpoints."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from ...db.models import FavoritesMonitor, Gallery
from ...db.repository import (
    FavoritesRepository,
    GalleryRepository,
    GalleryUpdatesRepository,
)
from ...logging import log_extra
from ...services.deletion import delete_galleries_local
from ...services.eh_client import EhClient, EhClientError, FavoriteData, GalleryGoneError
from ...services.favorites_worker import (
    FavoriteDownloadQueue,
    estimate_cloud_size,
    favorite_counts_cached,
    favorite_size_sync,
    favorites_metadata,
    remote_cover_data_batch,
    run_duplicates_scan,
    run_favorites_check,
)
from ...services.tag_translation import translated_tag
from ..dependencies import (
    db_error,
    display_title,
    get_current_settings,
    get_session,
    get_task_manager,
    image_content_type,
    resolve_display_title,
    spawn_task,
)
from ..schemas import (
    ArchivePreviewRequest,
    DownloadSelectedRequest,
    DuplicateIgnoreRequest,
    FavoriteCategoryRequest,
    FavoritesMoveRequest,
    FavoritesRemoveRequest,
)
from ..state import app_state

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_gdata_tags(raw_tags: list[Any]) -> list[tuple[str | None, str]]:
    out: list[tuple[str | None, str]] = []
    for tag in raw_tags or []:
        if isinstance(tag, dict):
            ns = str(tag.get("namespace") or "").strip() or None
            name = str(tag.get("name") or "").strip()
            if name:
                out.append((ns, name))
        elif isinstance(tag, (list, tuple)) and len(tag) >= 2:
            ns = str(tag[0] or "").strip() or None
            name = str(tag[1] or "").strip()
            if name:
                out.append((ns, name))
        elif isinstance(tag, str) and tag.strip():
            val = tag.strip()
            if ":" in val:
                ns, name = val.split(":", 1)
                out.append((ns.strip() or None, name.strip()))
            else:
                out.append((None, val))
    return out


def _unix_to_iso(val: Any) -> str | None:
    if val is None:
        return None
    try:
        ts = float(val)
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def _record_favorites_remove_log(
    gids: list[int],
    deleted_local_galleries: int,
    failed_deletions: list[str],
    cloud_failed: list[int],
) -> None:
    now = datetime.now(UTC).isoformat()
    status = "failed" if (cloud_failed or failed_deletions) else "success"
    reason = f"unfavorited {len(gids)}"
    if deleted_local_galleries:
        reason += f", deleted local {deleted_local_galleries}"
    if failed_deletions:
        reason += f", delete failed {len(failed_deletions)}: {', '.join(failed_deletions[:3])}"
        if len(failed_deletions) > 3:
            reason += f" (+{len(failed_deletions) - 3} more)"
    if cloud_failed:
        reason += f", cloud remove failed {len(cloud_failed)}: {', '.join(map(str, cloud_failed[:5]))}"
        if len(cloud_failed) > 5:
            reason += f" (+{len(cloud_failed) - 5} more)"

    tm = get_task_manager()
    tm.record_task(
        "favorites-remove",
        now,
        now,
        status,
        reason=reason,
        done=deleted_local_galleries,
        total=len(gids),
    )
    spawn_task(tm.persist_history(), "persist task history")


def _record_favorites_move_log(
    gids: list[int],
    target_favcat: int,
    cloud_failed: list[int],
    local_moved: int,
) -> None:
    now = datetime.now(UTC).isoformat()
    status = "failed" if cloud_failed else "success"
    reason = f"moved {local_moved} to #{target_favcat}"
    if cloud_failed:
        reason += f", cloud move failed {len(cloud_failed)}: {', '.join(map(str, cloud_failed[:5]))}"
        if len(cloud_failed) > 5:
            reason += f" (+{len(cloud_failed) - 5} more)"

    tm = get_task_manager()
    tm.record_task(
        "favorites-move",
        now,
        now,
        status,
        reason=reason,
        done=local_moved,
        total=len(gids),
    )
    spawn_task(tm.persist_history(), "persist task history")


@router.get("/api/favorites/{favcat}/items")
async def favorite_items(
    favcat: int, page: int = 1, page_size: int = 24, state: str = "all"
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    if state not in {"all", "local", "cloud"}:
        raise HTTPException(status_code=422, detail="invalid state")
    try:
        async for session in get_session():
            total, rows = await FavoritesRepository(session).list_items(
                favcat, page, page_size, state
            )
            tag_map = await GalleryRepository(session).tags_for_galleries(
                [g.id for _, g in rows if (g is not None) and g.id is not None]
            )
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    cloud_pairs = [
        (item.gid, item.token)
        for item, gallery in rows
        if gallery is None and item.token
    ]
    metadata = await favorites_metadata(cloud_pairs)
    for item, gallery in rows:
        if gallery is None and item.thumb:
            entry = metadata.setdefault(int(item.gid), {})
            if not entry.get("thumb"):
                entry["thumb"] = item.thumb
    cover_data = await remote_cover_data_batch(cloud_pairs, metadata)
    items = []
    for item, gallery in rows:
        if gallery is not None:
            title = display_title(gallery)
            title_jpn = gallery.title_jpn
            category = gallery.category or "other"
            page_count = gallery.page_count or 0
            cover_url = f"/api/galleries/{gallery.id}/thumb/0" if gallery.page_count else None
            file_size = getattr(gallery, "file_size", None) or getattr(gallery, "storage_size", 0)
            tags = [
                {
                    "namespace": ns,
                    "name": name,
                    "display": translated_tag(ns, name)[1],
                }
                for ns, name in tag_map.get(gallery.id, [])
            ]
        else:
            meta = metadata.get(item.gid, {})
            title = resolve_display_title(
                item.title or meta.get("title") or "",
                meta.get("title_jpn"),
            ) or f"gid {item.gid}"
            title_jpn = meta.get("title_jpn")
            category = meta.get("category")
            page_count = meta.get("file_count") or meta.get("filecount")
            cover_url = None
            file_size = meta.get("file_size") or item.file_size
            tags = [
                {
                    "namespace": ns,
                    "name": name,
                    "display": translated_tag(ns, name)[1],
                }
                for ns, name in _parse_gdata_tags(meta.get("tags", []))
            ]
        items.append(
            {
                "favcat": item.favcat,
                "gid": item.gid,
                "token": item.token,
                "title": title,
                "title_jpn": title_jpn,
                "url": item.url,
                "gallery_id": gallery.id if gallery is not None else None,
                "category": category,
                "page_count": page_count,
                "filecount": page_count,
                "cover_url": cover_url,
                "cover_data": cover_data.get(item.gid),
                "file_size": file_size,
                "filesize": file_size,
                "first_seen_at": item.first_seen_at,
                "is_local": gallery is not None,
                "tags": tags,
            }
        )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "state": state,
        "items": items,
    }


@router.post("/api/archives/preview")
async def archives_preview(body: ArchivePreviewRequest) -> dict[str, object]:
    """Read-only archive info for a set of gids (no GP is charged)."""
    gids = list(dict.fromkeys(body.gids))
    if not gids:
        raise HTTPException(status_code=422, detail="no galleries selected")
    client = app_state.eh_client
    if client is None:
        raise HTTPException(status_code=503, detail="ExHentai client is unavailable")
    try:
        async for session in get_session():
            detail = await FavoritesRepository(session).favorite_items_detail_by_gids(gids)
            if len(detail) < len(gids):
                missing = [g for g in gids if g not in detail]
                for row in await GalleryUpdatesRepository(session).by_new_gids(missing):
                    if row is not None:
                        detail[int(row.new_gid)] = {
                            "token": row.new_token,
                            "title": row.title or "",
                            "gallery_id": None,
                        }
                still_missing = [g for g in missing if g not in detail]
                if still_missing:
                    for row in (
                        await session.scalars(
                            select(Gallery).where(Gallery.gid.in_(still_missing))
                        )
                    ).all():
                        detail[int(row.gid)] = {
                            "token": row.token,
                            "title": row.title,
                            "gallery_id": row.id,
                        }
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    funds = await client.fetch_gp_balance()
    items: list[dict[str, object]] = []
    for gid in gids:
        entry = detail.get(gid)
        token = (entry or {}).get("token")
        if not token:
            continue
        try:
            info = await client.fetch_archive_info(int(gid), str(token))
        except (EhClientError, GalleryGoneError) as exc:
            items.append(
                {"gid": gid, "title": (entry or {}).get("title") or "", "error": str(exc)}
            )
            continue
        items.append(
            {
                "gid": gid,
                "title": (entry or {}).get("title") or "",
                "resample_cost": (
                    info.resample_cost if info.resample_url is not None else None
                ),
                "resample_size": (
                    info.resample_size if info.resample_url is not None else None
                ),
                "original_cost": (
                    info.original_cost if info.original_url is not None else None
                ),
                "original_size": (
                    info.original_size if info.original_url is not None else None
                ),
                "resample_available": (
                    info.resample_url is not None
                    and (funds is None or funds >= info.resample_cost)
                ),
                "original_available": (
                    info.original_url is not None
                    and (funds is None or funds >= info.original_cost)
                ),
            }
        )
    return {"funds": funds, "items": items}


@router.post("/api/favorites/download-selected", status_code=202)
async def favorites_download_selected(body: DownloadSelectedRequest) -> dict[str, object]:
    """Enqueue downloads for selected favorite gids."""
    gids = list(dict.fromkeys(body.gids))
    if not gids:
        raise HTTPException(status_code=422, detail="no galleries selected")
    mode = "favorite_archive" if body.archive else "favorite"
    quality = (body.quality or None) if body.archive else None
    try:
        async for session in get_session():
            detail = await FavoritesRepository(session).favorite_items_detail_by_gids(gids)
            if len(detail) < len(gids):
                missing = [g for g in gids if g not in detail]
                for row in await GalleryUpdatesRepository(session).by_new_gids(missing):
                    if row is not None:
                        detail[int(row.new_gid)] = {
                            "token": row.new_token,
                            "title": row.title or "",
                            "gallery_id": None,
                        }
                still_missing = [g for g in missing if g not in detail]
                if still_missing:
                    for row in (
                        await session.scalars(
                            select(Gallery).where(Gallery.gid.in_(still_missing))
                        )
                    ).all():
                        detail[int(row.gid)] = {
                            "token": row.token,
                            "title": row.title,
                            "gallery_id": row.id,
                        }
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    queue = FavoriteDownloadQueue()
    queued = 0
    skipped = 0
    for gid in gids:
        entry = detail.get(gid)
        if not entry or not entry.get("token") or entry.get("gallery_id") is not None:
            skipped += 1
            continue
        try:
            ok = await queue.enqueue(
                FavoriteData(
                    gid=gid,
                    token=entry["token"],
                    title=entry.get("title") or str(gid),
                    url=entry.get("url") or "",
                ),
                mode=mode,
                quality=quality,
            )
        except Exception:  # noqa: BLE001
            ok = False
        if ok:
            queued += 1
        else:
            skipped += 1
    return {"queued": queued, "skipped": skipped}


# Backward compatibility alias
favorites_download_batch = favorites_download_selected
router.add_api_route(
    "/api/favorites/download-batch",
    favorites_download_selected,
    methods=["POST"],
    status_code=202,
)


@router.post("/api/favorites/sync")
async def favorites_sync() -> dict[str, object]:
    client = app_state.eh_client
    if client is None:
        raise HTTPException(status_code=503, detail="ExHentai client is unavailable")
    try:
        async for session in get_session():
            categories = await FavoritesRepository(session).categories()
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"status": "ok", "categories": len(categories)}


@router.post("/api/favorites/remove")
async def favorites_remove(body: FavoritesRemoveRequest) -> dict[str, object]:
    if not body.gids:
        raise HTTPException(status_code=422, detail="no galleries selected")
    gids = list(dict.fromkeys(body.gids))
    cloud_failed: list[int] = []
    cloud_removed = 0
    cloud_ok = True
    settings = get_current_settings()
    try:
        client = app_state.eh_client
        if client is not None:
            cloud_failed = await client.remove_favorites(gids)
        else:
            async with EhClient(settings, max_concurrency=settings.exhentai_max_concurrency) as temp_client:
                cloud_failed = await temp_client.remove_favorites(gids)
        cloud_removed = len(gids) - len(cloud_failed)
        cloud_ok = not cloud_failed
    except Exception as exc:  # noqa: BLE001
        cloud_ok = False
        cloud_failed = list(gids)
        logger.warning("cloud favorite removal failed", extra=log_extra(error=type(exc).__name__))

    local_removed = 0
    deleted_local_galleries = 0
    failed_deletions: list[str] = []
    try:
        async for session in get_session():
            async with session.begin():
                if body.delete_local or body.delete_files:
                    mapping = await FavoritesRepository(session).galleries_for_gids(gids)
                    galleries: list[Gallery] = []
                    for gallery_id in mapping.values():
                        gallery = await session.get(Gallery, gallery_id)
                        if gallery is not None:
                            galleries.append(gallery)
                    results = await delete_galleries_local(
                        session, galleries, delete_files=True, delete_all_copies=body.delete_all_copies
                    )
                    deleted_local_galleries = sum(1 for r in results if r.get("db_removed"))
                    for r in results:
                        failed_deletions.extend(r.get("failed_paths", []))
                local_removed = await FavoritesRepository(session).remove_gids(gids)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    if body.delete_local or body.delete_files:
        _record_favorites_remove_log(
            gids, deleted_local_galleries, failed_deletions, cloud_failed
        )
    return {
        "gids": gids,
        "cloud_ok": cloud_ok,
        "cloud_removed": cloud_removed,
        "cloud_failed": cloud_failed,
        "local_removed": local_removed,
        "deleted_local_galleries": deleted_local_galleries,
        "failed_deletions": failed_deletions,
    }


@router.post("/api/favorites/move")
async def favorites_move(body: FavoritesMoveRequest) -> dict[str, object]:
    if not body.gids:
        raise HTTPException(status_code=422, detail="no galleries selected")
    gids = list(dict.fromkeys(body.gids))
    cloud_failed: list[int] = []
    cloud_moved = 0
    cloud_ok = True
    settings = get_current_settings()
    try:
        client = app_state.eh_client
        if client is not None:
            cloud_failed = await client.move_favorites(gids, body.target_favcat)
        else:
            async with EhClient(settings, max_concurrency=settings.exhentai_max_concurrency) as temp_client:
                cloud_failed = await temp_client.move_favorites(gids, body.target_favcat)
        cloud_moved = len(gids) - len(cloud_failed)
        cloud_ok = not cloud_failed
    except Exception as exc:  # noqa: BLE001
        cloud_ok = False
        cloud_failed = list(gids)
        logger.warning("cloud favorite move failed", extra=log_extra(error=type(exc).__name__))

    successful_gids = [g for g in gids if g not in set(cloud_failed)]
    local_moved = 0
    if successful_gids:
        try:
            async for session in get_session():
                async with session.begin():
                    local_moved = await FavoritesRepository(session).move_gids(
                        successful_gids, body.target_favcat
                    )
                break
        except SQLAlchemyError as exc:
            raise db_error(exc) from exc

    _record_favorites_move_log(gids, body.target_favcat, cloud_failed, local_moved)

    return {
        "gids": gids,
        "target_favcat": body.target_favcat,
        "cloud_ok": cloud_ok,
        "cloud_moved": cloud_moved,
        "cloud_failed": cloud_failed,
        "local_moved": local_moved,
    }


@router.post("/api/favorites/duplicates/scan", status_code=202)
async def duplicates_scan() -> dict[str, object]:
    tm = get_task_manager()
    if tm.duplicates_state.get("running"):
        raise HTTPException(status_code=409, detail="scan already running")
    spawn_task(run_duplicates_scan(), "duplicates scan")
    return {"started": True}


@router.get("/api/favorites/duplicates/status")
async def duplicates_status() -> dict[str, object]:
    tm = get_task_manager()
    groups = tm.duplicates_state.get("groups") or []
    total_items = sum(len(g["items"]) for g in groups)
    return {
        "running": bool(tm.duplicates_state.get("running")),
        "stage": tm.duplicates_state.get("stage"),
        "done": tm.duplicates_state.get("done", 0),
        "total": tm.duplicates_state.get("total", 0),
        "last_error": tm.duplicates_state.get("last_error"),
        "groups": groups,
        "group_count": len(groups),
        "item_count": total_items,
        "ignored": tm.duplicates_state.get("ignored") or [],
    }


@router.get("/api/favorites/duplicates/ignored")
async def duplicates_ignored_list() -> list[dict[str, object]]:
    try:
        async for session in get_session():
            ignores = await FavoritesRepository(session).ignored_duplicates()
            all_gids = [gid for entry in ignores for gid in (entry.get("gids") or [])]
            items: dict[int, dict] = {}
            if all_gids:
                items = await FavoritesRepository(session).favorite_items_detail_by_gids(all_gids)
                cloud_pairs = [
                    (gid, str(detail.get("token") or ""))
                    for gid, detail in items.items()
                    if detail.get("gallery_id") is None and detail.get("token")
                ]
                gmeta = await favorites_metadata(cloud_pairs) if cloud_pairs else {}
                cover_map = await remote_cover_data_batch(cloud_pairs, gmeta)
                for gid, detail in items.items():
                    tags = detail.get("tags") or []
                    if tags:
                        detail["tags"] = [
                            {
                                "namespace": tag.get("namespace"),
                                "name": tag.get("name"),
                                "display": translated_tag(tag.get("namespace"), tag.get("name"))[1],
                            }
                            for tag in tags
                        ]
                    if detail.get("gallery_id") is not None:
                        continue
                    meta = gmeta.get(gid, {})
                    detail["cover_data"] = cover_map.get(gid)
                    detail["file_size"] = detail.get("file_size") or meta.get("file_size")
                    detail["posted_at"] = detail.get("posted_at") or _unix_to_iso(meta.get("posted"))
                    if meta.get("tags"):
                        detail["tags"] = [
                            {
                                "namespace": ns,
                                "name": name,
                                "display": translated_tag(ns, name)[1],
                            }
                            for ns, name in _parse_gdata_tags(meta.get("tags", []))
                        ]
            return [
                {**entry, "items": [items.get(gid) for gid in (entry.get("gids") or []) if gid in items]}
                for entry in ignores
            ]
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc


@router.post("/api/favorites/duplicates/ignore")
async def duplicates_ignore(body: DuplicateIgnoreRequest) -> dict[str, object]:
    if not body.key.strip():
        raise HTTPException(status_code=422, detail="invalid key")
    try:
        async for session in get_session():
            async with session.begin():
                await FavoritesRepository(session).add_duplicate_ignore(
                    body.key.strip(), body.title, body.gids
                )
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"ok": True, "key": body.key.strip()}


@router.delete("/api/favorites/duplicates/ignore")
@router.post("/api/favorites/duplicates/unignore")
async def duplicates_unignore(key: str = "") -> dict[str, object]:
    if not key.strip():
        raise HTTPException(status_code=422, detail="invalid key")
    try:
        async for session in get_session():
            async with session.begin():
                await FavoritesRepository(session).remove_duplicate_ignore(key.strip())
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"ok": True, "key": key.strip()}


@router.get("/api/favorites/cover")
async def favorite_cover(gid: int, token: str) -> Response:
    settings = get_current_settings()
    if not settings.exhentai_cookies:
        raise HTTPException(status_code=422, detail="ExHentai Cookie 未设置")
    if not re.fullmatch(r"[0-9a-fA-F]{8,64}", token):
        raise HTTPException(status_code=422, detail="invalid token")
    cache_dir = Path(settings.thumbnail_cache_dir).parent / "remote-covers"
    path = cache_dir / f"{int(gid)}.img"
    if not await run_in_threadpool(path.is_file):
        client = app_state.eh_client
        if client is None:
            raise HTTPException(status_code=503, detail="ExHentai client is unavailable")
        try:
            data, _ = await client.fetch_gallery_cover(int(gid), token)
        except (GalleryGoneError, EhClientError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        def _write_atomic() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)

        await run_in_threadpool(_write_atomic)
    # Infer content-type from first bytes without loading whole file twice.
    head: bytes = await run_in_threadpool(lambda: path.read_bytes()[:16])
    return FileResponse(
        path,
        media_type=image_content_type(head),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/api/favorites/categories")
async def favorite_categories() -> list[dict[str, object]]:
    try:
        async for session in get_session():
            rows = await FavoritesRepository(session).categories()
            stats = await FavoritesRepository(session).counts_and_sizes()
            breakdown = {
                row.favcat: await FavoritesRepository(session).cloud_size_breakdown(row.favcat)
                for row in rows
            }
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    live_counts: dict[int, int] = {}
    try:
        live_counts = await favorite_counts_cached()
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not fetch live favorite counts", extra=log_extra(error=type(exc).__name__))
    result = []
    for x in rows:
        cloud, local, local_size = stats.get(x.favcat, (0, 0, 0))
        cloud_count = live_counts.get(x.favcat, cloud)
        known, unknown = breakdown.get(x.favcat, (0, 0))
        if unknown > 0 and local > 0:
            known += int((local_size / local) * unknown)
        result.append(
            {
                "favcat": x.favcat,
                "name": x.name,
                "enabled": x.enabled,
                "mode": x.mode,
                "poll_interval_minutes": max(1, round(x.poll_interval_seconds / 60)),
                "cloud_count": cloud_count,
                "local_count": local,
                "local_size": local_size,
                "cloud_size": known or estimate_cloud_size(cloud_count, local, local_size),
            }
        )
    return result


@router.get("/api/favorites/metadata-status")
async def favorites_metadata_status() -> dict[str, object]:
    tm = get_task_manager()
    return dict(tm.metadata_sync_state)


@router.get("/api/favorites/check-status")
async def favorites_check_status() -> dict[str, object]:
    tm = get_task_manager()
    return dict(tm.favorites_check_state)


@router.post("/api/favorites/compute-sizes", status_code=202)
async def compute_favorite_sizes() -> dict[str, object]:
    favcats: list[int] = []
    async for session in get_session():
        favcats = [row.favcat for row in await FavoritesRepository(session).categories()]
        break
    for favcat in favcats:
        spawn_task(favorite_size_sync(favcat), f"favorite size sync {favcat}")
    return {"status": "started", "favcats": favcats}


@router.post("/api/favorites/download-missing", status_code=202)
async def download_missing_favorites() -> dict[str, object]:
    favcats: list[int] = []
    async for session in get_session():
        favcats = [row.favcat for row in await FavoritesRepository(session).categories()]
        break
    if not favcats:
        favcats = list(range(10))
    for favcat in favcats:
        spawn_task(favorite_size_sync(favcat), f"favorite metadata sync {favcat}")
    return {"status": "started", "favcats": favcats}


@router.post("/api/favorites/categories")
async def update_favorite_category(
    body: FavoriteCategoryRequest, favcat: int = 0
) -> dict[str, object]:
    favcat = body.favcat if body.favcat is not None else favcat
    if not 0 <= favcat <= 9:
        raise HTTPException(status_code=422, detail="invalid favcat")
    try:
        async for session in get_session():
            async with session.begin():
                row = await FavoritesRepository(session).category(favcat)
                if row is None:
                    row = FavoritesMonitor(favcat=favcat)
                    session.add(row)
                if body.enabled is not None:
                    row.enabled = body.enabled
                if body.mode is not None:
                    row.mode = body.mode
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"favcat": favcat, "enabled": row.enabled, "mode": row.mode}


@router.post("/api/favorites/sync-categories")
@router.post("/api/favorites/fetch-categories")
async def sync_favorite_categories() -> list[dict[str, object]]:
    settings = get_current_settings()
    if not settings.exhentai_cookies:
        raise HTTPException(status_code=422, detail="ExHentai Cookie 未设置")
    if app_state.eh_client is None:
        raise HTTPException(status_code=503, detail="ExHentai client is unavailable")
    try:
        names = await app_state.eh_client.fetch_favorite_categories()
        async for session in get_session():
            async with session.begin():
                if isinstance(names, dict):
                    for favcat, name in names.items():
                        row = await FavoritesRepository(session).category(favcat)
                        if row is None:
                            row = FavoritesMonitor(favcat=favcat)
                            session.add(row)
                        row.name = name
                elif isinstance(names, list):
                    for favcat, name in enumerate(names):
                        row = await FavoritesRepository(session).category(favcat)
                        if row is None:
                            row = FavoritesMonitor(favcat=favcat)
                            session.add(row)
                        row.name = name
            break
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "favorite category synchronization failed", extra=log_extra(error=type(exc).__name__)
        )
        raise HTTPException(status_code=503, detail="无法读取 ExHentai 收藏夹分类") from exc
    if isinstance(names, dict):
        return [{"favcat": favcat, "name": name} for favcat, name in names.items()]
    return [{"favcat": favcat, "name": name} for favcat, name in enumerate(names)]


@router.post("/api/favorites/{favcat}/check", status_code=202)
@router.post("/api/favorites/check", status_code=202)
async def check_favorites(favcat: int = 0) -> dict[str, object]:
    if not 0 <= favcat <= 9:
        raise HTTPException(status_code=422, detail="invalid favcat")
    service = app_state.favorites_service
    if service is None:
        raise HTTPException(status_code=503, detail="Favorites service is unavailable")
    spawn_task(run_favorites_check(favcat, service), "favorites check")
    return {"status": "started", "favcat": favcat}


@router.post("/api/favorites/check-all", status_code=202)
async def check_all_favorites() -> dict[str, object]:
    service = app_state.favorites_service
    if service is None:
        raise HTTPException(status_code=503, detail="Favorites service is unavailable")
    try:
        async for session in get_session():
            categories = await FavoritesRepository(session).categories()
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    favcats = [int(c.favcat) for c in categories] or list(range(10))
    for favcat in favcats:
        spawn_task(run_favorites_check(favcat, service), f"favorites check {favcat}")
    return {"status": "started", "favcats": favcats}
