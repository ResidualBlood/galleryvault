"""
Favorites endpoints.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from galleryvault.app import main
from galleryvault.db.models import Gallery
from galleryvault.db.repository import (
    FavoritesRepository,
    GalleryRepository,
    GalleryUpdatesRepository,
)
from galleryvault.logging import log_extra
from galleryvault.services.eh_client import EhClientError, FavoriteData, GalleryGoneError
from galleryvault.services.tag_translation import translated_tag

router = APIRouter()

@router.get("/api/favorites/{favcat}/items")
async def favorite_items(
    favcat: int, page: int = 1, page_size: int = 24, state: str = "all"
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    if state not in {"all", "local", "cloud"}:
        raise HTTPException(status_code=422, detail="invalid state")
    try:
        async with main._settings_session() as session:
            total, rows = await FavoritesRepository(session).list_items(
                favcat, page, page_size, state
            )
            tag_map = await GalleryRepository(session).tags_for_galleries(
                [
                    g.id
                    for _, g in rows
                    if (g is not None) and g.id is not None
                ]
            )
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    cloud_pairs = [
        (item.gid, item.token)
        for item, gallery in rows
        if gallery is None and item.token
    ]
    metadata = await main._favorites_metadata(cloud_pairs)
    # Cached cloud items come back with an empty gdata thumb; fall back to the
    # thumb URL captured from the favorites listing so a missing disk cover can
    # still be fetched lazily while browsing.
    for item, gallery in rows:
        if gallery is None and item.thumb:
            entry = metadata.setdefault(int(item.gid), {})
            if not entry.get("thumb"):
                entry["thumb"] = item.thumb
    cover_data = await main._remote_cover_data_batch(cloud_pairs, metadata)
    items = []
    for item, gallery in rows:
        if gallery is not None:
            title = main.display_title(gallery)
            title_jpn = gallery.title_jpn
            category = gallery.category or "other"
            page_count = gallery.page_count or 0
            cover_url = f"/api/galleries/{gallery.id}/thumb/0" if gallery.page_count else None
            file_size = gallery.file_size
            tags = [
                {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
                for ns, name in tag_map.get(gallery.id, [])
            ]
        else:
            meta = metadata.get(item.gid, {})
            title = main.resolve_display_title(
                item.title or meta.get("title") or "",
                meta.get("title_jpn"),
            ) or f"gid {item.gid}"
            title_jpn = meta.get("title_jpn")
            category = meta.get("category")
            page_count = meta.get("file_count")
            cover_url = None
            file_size = meta.get("file_size") or item.file_size
            tags = [
                {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
                for ns, name in main._parse_gdata_tags(meta.get("tags", []))
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
                "cover_url": cover_url,
                "cover_data": cover_data.get(item.gid),
                "file_size": file_size,
                "first_seen_at": item.first_seen_at,
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


class DownloadSelectedRequest(BaseModel):
    gids: list[int]
    archive: bool = False
    quality: str | None = None


class ArchivePreviewRequest(BaseModel):
    gids: list[int]


@router.post("/api/archives/preview")
async def archives_preview(body: ArchivePreviewRequest) -> dict[str, object]:
    """Read-only archive info for a set of gids (no GP is charged).

    Returns the current funds balance plus per-gallery original/resample cost
    and size so the dialog can render tiers and availability before confirming.
    Tokens are resolved from the favorites table (and gallery-update rows).
    """
    gids = list(dict.fromkeys(body.gids))
    if not gids:
        raise HTTPException(status_code=422, detail="no galleries selected")
    client = main.app.state.eh_client
    if client is None:
        raise HTTPException(status_code=503, detail="ExHentai client is unavailable")
    try:
        async with main._settings_session() as session:
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
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    funds: int | None = None
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
        if funds is None and info.funds is not None:
            funds = info.funds
        items.append(
            {
                "gid": gid,
                "title": (entry or {}).get("title") or "",
                # Unavailable tiers (``N/A`` on the archiver page) report null
                # cost/size so the frontend can show ``N/A`` instead of a
                # misleading ``0 GP · 0 B``; GP-shortage tiers keep real values
                # and merely report ``*_available`` false.
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
                    and (info.funds is None or info.funds >= info.resample_cost)
                ),
                "original_available": (
                    info.original_url is not None
                    and (info.funds is None or info.funds >= info.original_cost)
                ),
            }
        )
    return {"funds": funds, "items": items}


@router.post("/api/favorites/download-selected", status_code=202)
async def favorites_download_selected(body: DownloadSelectedRequest) -> dict[str, object]:
    """Enqueue downloads for the selected favorite gids directly from the DB.

    Unlike the SPA's old flow (which paged through the whole folder to build
    token metadata), this looks the items up in one query — instant even for
    folders with thousands of cloud-only galleries.  ``archive=True`` downloads
    through the ExHentai archive (zip) channel with the given quality tier.
    """
    gids = list(dict.fromkeys(body.gids))
    if not gids:
        raise HTTPException(status_code=422, detail="no galleries selected")
    mode = "favorite_archive" if body.archive else "favorite"
    quality = (body.quality or None) if body.archive else None
    try:
        async with main._settings_session() as session:
            detail = await FavoritesRepository(session).favorite_items_detail_by_gids(gids)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    queue = main._FavoriteDownloadQueue()
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
        except Exception:  # noqa: BLE001 - one gid must not fail the batch
            ok = False
        if ok:
            queued += 1
        else:
            skipped += 1
    return {"queued": queued, "skipped": skipped}


@router.post("/api/favorites/remove")
async def favorites_remove(body: main.FavoritesRemoveRequest) -> dict[str, object]:
    if not body.gids:
        raise HTTPException(status_code=422, detail="no galleries selected")
    gids = list(dict.fromkeys(body.gids))
    cloud_failed: list[int] = []
    cloud_removed = 0
    cloud_ok = True
    try:
        client = main.app.state.eh_client
        if client is not None:
            # Shared global client: never enter its async context, that would
            # close the underlying httpx client for every other worker.
            cloud_failed = await client.remove_favorites(gids)
        else:
            async with main.EhClient(
                main._settings(), max_concurrency=main._settings().exhentai_max_concurrency
            ) as temp_client:
                cloud_failed = await temp_client.remove_favorites(gids)
        cloud_removed = len(gids) - len(cloud_failed)
        cloud_ok = not cloud_failed
    except Exception as exc:  # noqa: BLE001 - cloud is best-effort, keep going
        cloud_ok = False
        cloud_failed = list(gids)
        main.logger.warning(
            "cloud favorite removal failed",
            extra=log_extra(error=type(exc).__name__),
        )
    local_removed = 0
    deleted_local_galleries = 0
    failed_deletions: list[str] = []
    try:
        async with main._settings_session() as session, session.begin():
            if body.delete_local:
                mapping = await FavoritesRepository(session).galleries_for_gids(gids)
                galleries: list[Gallery] = []
                for gallery_id in mapping.values():
                    gallery = await session.get(Gallery, gallery_id)
                    if gallery is not None:
                        galleries.append(gallery)
                results = await main.delete_galleries_local(
                    session, galleries, delete_files=True, delete_all_copies=True
                )
                deleted_local_galleries = sum(1 for r in results if r["db_removed"])
                for r in results:
                    failed_deletions.extend(r["failed_paths"])
            local_removed = await FavoritesRepository(session).remove_gids(gids)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    if body.delete_local:
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


@router.post("/api/favorites/duplicates/scan", status_code=202)
async def duplicates_scan() -> dict[str, object]:
    if main.duplicates_state["running"]:
        raise HTTPException(status_code=409, detail="scan already running")
    main._spawn(main._run_duplicates_scan(), "duplicates scan")
    return {"started": True}


@router.get("/api/favorites/duplicates/status")
async def duplicates_status() -> dict[str, object]:
    groups = main.duplicates_state.get("groups") or []
    total_items = sum(len(g["items"]) for g in groups)
    return {
        "running": bool(main.duplicates_state["running"]),
        "stage": main.duplicates_state.get("stage"),
        "done": main.duplicates_state.get("done", 0),
        "total": main.duplicates_state.get("total", 0),
        "last_error": main.duplicates_state.get("last_error"),
        "groups": groups,
        "group_count": len(groups),
        "item_count": total_items,
        "ignored": main.duplicates_state.get("ignored") or [],
    }


@router.get("/api/favorites/duplicates/ignored")
async def duplicates_ignored_list() -> list[dict[str, object]]:
    try:
        async with main._settings_session() as session:
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
                gmeta = await main._favorites_metadata(cloud_pairs) if cloud_pairs else {}
                cover_map = await main._remote_cover_data_batch(cloud_pairs, gmeta)
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
                    detail["posted_at"] = detail.get("posted_at") or main._unix_to_iso(meta.get("posted"))
                    if meta.get("tags"):
                        detail["tags"] = [
                            {
                                "namespace": ns,
                                "name": name,
                                "display": translated_tag(ns, name)[1],
                            }
                            for ns, name in main._parse_gdata_tags(meta.get("tags", []))
                        ]
            return [
                {**entry, "items": [items.get(gid) for gid in (entry.get("gids") or []) if gid in items]}
                for entry in ignores
            ]
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc


@router.post("/api/favorites/duplicates/ignore")
async def duplicates_ignore(body: main.DuplicateIgnoreRequest) -> dict[str, object]:
    if not body.key.strip():
        raise HTTPException(status_code=422, detail="invalid key")
    try:
        async with main._settings_session() as session, session.begin():
            await FavoritesRepository(session).add_duplicate_ignore(
                body.key.strip(), body.title, body.gids
            )
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    return {"ok": True, "key": body.key.strip()}


@router.delete("/api/favorites/duplicates/ignore")
async def duplicates_unignore(key: str) -> dict[str, object]:
    if not key.strip():
        raise HTTPException(status_code=422, detail="invalid key")
    try:
        async with main._settings_session() as session, session.begin():
            await FavoritesRepository(session).remove_duplicate_ignore(key.strip())
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    return {"ok": True, "key": key.strip()}


@router.get("/api/galleries/{identifier}/favorite")
async def gallery_favorite_status(identifier: int) -> dict[str, object]:
    try:
        async with main._settings_session() as session:
            row, _ = await main._gallery(identifier)
            favcats = await FavoritesRepository(session).favcats_for_gid(row.gid)
            names = await FavoritesRepository(session).category_names(favcats)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    return {
        "gid": row.gid,
        "favorite": bool(favcats),
        "favcats": favcats,
        "favcat_names": [{"favcat": f, "name": names.get(f, "")} for f in favcats],
    }


@router.get("/api/favorites/cover")
async def favorite_cover(gid: int, token: str) -> Response:
    """Proxy an ExHentai gallery cover for a not-yet-local favorite item.

    Cached under ``/gv-cache/remote-covers/{gid}.img`` so repeated lists do not
    re-fetch ExHentai.
    """
    if not main._settings().exhentai_cookies:
        raise HTTPException(status_code=422, detail="ExHentai Cookie 未设置")
    if not re.fullmatch(r"[0-9a-fA-F]{8,64}", token):
        raise HTTPException(status_code=422, detail="invalid token")
    cache_dir = Path(main._settings().thumbnail_cache_dir).parent / "remote-covers"
    path = cache_dir / f"{int(gid)}.img"
    if not path.is_file():
        client = main.app.state.eh_client
        if client is None:
            raise HTTPException(status_code=503, detail="ExHentai client is unavailable")
        try:
            data, _ = await client.fetch_gallery_cover(int(gid), token)
        except (GalleryGoneError, EhClientError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    body = path.read_bytes()
    return Response(
        body,
        media_type=main._image_content_type(body),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/api/favorites/categories")
async def favorite_categories() -> list[dict[str, object]]:
    try:
        async with main._settings_session() as session:
            rows = await FavoritesRepository(session).categories()
            stats = await FavoritesRepository(session).counts_and_sizes()
            breakdown = {
                row.favcat: await FavoritesRepository(session).cloud_size_breakdown(row.favcat)
                for row in rows
            }
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    live_counts: dict[int, int] = {}
    try:
        live_counts = await main._favorite_counts_cached()
    except Exception as exc:  # noqa: BLE001 - fall back to recorded counts
        main.logger.warning(
            "could not fetch live favorite counts", extra=log_extra(error=type(exc).__name__)
        )
    result = []
    for x in rows:
        cloud, local, local_size = stats.get(x.favcat, (0, 0, 0))
        cloud_count = live_counts.get(x.favcat, cloud)
        known, unknown = breakdown.get(x.favcat, (0, 0))
        if unknown > 0 and local > 0:
            known += int((local_size / local) * unknown)  # estimate the unfetched tail
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
                "cloud_size": known or main._estimate_cloud_size(cloud_count, local, local_size),
            }
        )
    return result


@router.get("/api/favorites/metadata-status")
async def favorites_metadata_status() -> dict[str, object]:
    return dict(main.metadata_sync_state)


@router.get("/api/favorites/check-status")
async def favorites_check_status() -> dict[str, object]:
    return dict(main.favorites_check_state)


@router.post("/api/favorites/compute-sizes", status_code=202)
async def compute_favorite_sizes() -> dict[str, object]:
    """Fetch missing gallery sizes in the background for exact cloud sizes."""
    async with main._settings_session() as session:
        favcats = [row.favcat for row in await FavoritesRepository(session).categories()]
    for favcat in favcats:
        main._spawn(main._favorite_size_sync(favcat), f"favorite size sync {favcat}")
    return {"status": "started", "favcats": favcats}


@router.post("/api/favorites/download-missing", status_code=202)
async def download_missing_favorites() -> dict[str, object]:
    """Backfill missing cover files, tags and sizes for every favorite folder.

    Runs the same metadata sync as a post-check pass: for each folder it warms
    ``/gv-cache/remote-covers`` from the thumb URLs captured by the check,
    fetches gdata for items still missing metadata, and applies it to local
    galleries.  Progress is reported under ``/api/favorites/metadata-status``
    (visible on the Logs page) and the task can be cancelled via
    ``POST /api/logs/metadata/cancel``.
    """
    async with main._settings_session() as session:
        favcats = [row.favcat for row in await FavoritesRepository(session).categories()]
    if not favcats:
        favcats = list(range(10))
    for favcat in favcats:
        main._spawn(main._favorite_size_sync(favcat), f"favorite metadata sync {favcat}")
    return {"status": "started", "favcats": favcats}


@router.post("/api/favorites/categories")
async def update_favorite_category(
    body: main.FavoriteCategoryRequest, favcat: int = 0
) -> dict[str, object]:
    favcat = body.favcat if body.favcat is not None else favcat
    if not 0 <= favcat <= 9:
        raise HTTPException(status_code=422, detail="invalid favcat")
    try:
        async with main._settings_session() as session, session.begin():
            row = await FavoritesRepository(session).category(favcat)
            if row is None:
                from ..db.models import FavoritesMonitor

                row = FavoritesMonitor(favcat=favcat)
                session.add(row)
            if body.enabled is not None:
                row.enabled = body.enabled
            if body.mode is not None:
                row.mode = body.mode
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    return {"favcat": favcat, "enabled": row.enabled, "mode": row.mode}


@router.post("/api/favorites/sync-categories")
async def sync_favorite_categories() -> list[dict[str, object]]:
    if not main._settings().exhentai_cookies:
        raise HTTPException(status_code=422, detail="ExHentai Cookie 未设置")
    try:
        names = await main.app.state.eh_client.fetch_favorite_categories()
        async with main._settings_session() as session, session.begin():
            for favcat, name in names.items():
                row = await FavoritesRepository(session).category(favcat)
                if row is None:
                    from ..db.models import FavoritesMonitor

                    row = FavoritesMonitor(favcat=favcat)
                    session.add(row)
                row.name = name
    except HTTPException:
        raise
    except Exception as exc:
        main.logger.warning(
            "favorite category synchronization failed", extra=log_extra(error=type(exc).__name__)
        )
        raise HTTPException(status_code=503, detail="无法读取 ExHentai 收藏夹分类") from exc
    return [{"favcat": favcat, "name": name} for favcat, name in names.items()]


@router.post("/api/favorites/{favcat}/check", status_code=202)
async def check_favorites(favcat: int) -> dict[str, object]:
    if not 0 <= favcat <= 9:
        raise HTTPException(status_code=422, detail="invalid favcat")
    service = main.app.state.favorites_service
    if service is None:
        raise HTTPException(status_code=503, detail="Favorites service is unavailable")
    main._spawn(main._run_favorites_check(favcat, service), "favorites check")
    return {"status": "started", "favcat": favcat}


@router.post("/api/favorites/check-all", status_code=202)
async def check_all_favorites() -> dict[str, object]:
    service = main.app.state.favorites_service
    if service is None:
        raise HTTPException(status_code=503, detail="Favorites service is unavailable")
    try:
        async with main._settings_session() as session:
            cats = await FavoritesRepository(session).categories()
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    favcats = [int(c.favcat) for c in cats] or list(range(10))
    for favcat in favcats:
        main._spawn(main._run_favorites_check(favcat, service), f"favorites check {favcat}")
    return {"status": "started", "favcats": favcats}


def _record_favorites_remove_log(
    gids: list[int],
    deleted_local_galleries: int,
    failed_deletions: list[str],
    cloud_failed_gids: list[int] | None = None,
) -> None:
    """Append a favorites-remove entry to the activity log (Logs page)."""
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    reason = f"unfavorited {len(gids)}"
    if deleted_local_galleries:
        reason += f", deleted local {deleted_local_galleries}"
    if failed_deletions:
        reason += f", delete failed {len(failed_deletions)}: {', '.join(failed_deletions[:3])}"
        if len(failed_deletions) > 3:
            reason += f" (+{len(failed_deletions) - 3} more)"
    cloud_failed = cloud_failed_gids or []
    if cloud_failed:
        reason += f", cloud remove failed {len(cloud_failed)}: {', '.join(map(str, cloud_failed[:5]))}"
        if len(cloud_failed) > 5:
            reason += f" (+{len(cloud_failed) - 5} more)"
    failed = bool(failed_deletions) or bool(cloud_failed)
    main._record_task(
        "favorites-remove",
        now,
        now,
        "failed" if failed else "success",
        reason=reason,
        done=deleted_local_galleries,
        total=len(gids),
    )

