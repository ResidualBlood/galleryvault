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
from galleryvault.db.repository import FavoritesRepository, GalleryRepository
from galleryvault.logging import log_extra
from galleryvault.services.eh_client import EhClientError, FavoriteData, GalleryGoneError
from galleryvault.services.tag_translation import translated_tag

router = APIRouter()

@router.get("/api/favorites/{favcat}/items")
async def favorite_items(
    favcat: int, page: int = 1, page_size: int = 24
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    try:
        async with main._settings_session() as session:
            total, rows = await FavoritesRepository(session).list_items(
                favcat, page, page_size
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
    metadata: dict[int, dict[str, object]] = {}
    if cloud_pairs and main.app.state.eh_client is not None:
        try:
            metadata = await main.app.state.eh_client.fetch_gmetadata(cloud_pairs)
        except Exception as exc:  # noqa: BLE001 - covers/metadata are best-effort
            main.logger.warning(
                "favorite gdata fetch failed", extra=log_extra(error=type(exc).__name__)
            )
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
            title = item.title or meta.get("title") or f"gid {item.gid}"
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
    return {"total": total, "page": page, "page_size": page_size, "items": items}


class DownloadSelectedRequest(BaseModel):
    gids: list[int]


@router.post("/api/favorites/download-selected", status_code=202)
async def favorites_download_selected(body: DownloadSelectedRequest) -> dict[str, object]:
    """Enqueue downloads for the selected favorite gids directly from the DB.

    Unlike the SPA's old flow (which paged through the whole folder to build
    token metadata), this looks the items up in one query — instant even for
    folders with thousands of cloud-only galleries.
    """
    gids = list(dict.fromkeys(body.gids))
    if not gids:
        raise HTTPException(status_code=422, detail="no galleries selected")
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
                )
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
    cloud_removed = 0
    cloud_ok = True
    try:
        client = main.app.state.eh_client
        if client is not None:
            # Shared global client: never enter its async context, that would
            # close the underlying httpx client for every other worker.
            await client.remove_favorites(gids)
        else:
            async with main.EhClient(
                main._settings(), max_concurrency=main._settings().exhentai_max_concurrency
            ) as temp_client:
                await temp_client.remove_favorites(gids)
        cloud_removed = len(gids)
    except Exception as exc:  # noqa: BLE001 - cloud is best-effort, keep going
        cloud_ok = False
        main.logger.warning(
            "cloud favorite removal failed",
            extra=log_extra(error=type(exc).__name__),
        )
    local_removed = 0
    deleted_local_galleries = 0
    try:
        async with main._settings_session() as session, session.begin():
            if body.delete_local:
                mapping = await FavoritesRepository(session).galleries_for_gids(gids)
                for gallery_id in mapping.values():
                    gallery = await session.get(Gallery, gallery_id)
                    if gallery is None:
                        continue
                    await GalleryRepository(session).delete_ids([gallery_id])
                    main._remove_gallery_files(gallery)
                    deleted_local_galleries += 1
            local_removed = await FavoritesRepository(session).remove_gids(gids)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    return {
        "gids": gids,
        "cloud_ok": cloud_ok,
        "cloud_removed": cloud_removed,
        "local_removed": local_removed,
        "deleted_local_galleries": deleted_local_galleries,
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
                gmeta: dict[int, dict[str, object]] = {}
                if cloud_pairs and main.app.state.eh_client is not None:
                    try:
                        gmeta = await main.app.state.eh_client.fetch_gmetadata(cloud_pairs)
                    except Exception:  # noqa: BLE001 - best-effort
                        gmeta = {}
                cover_map = await main._remote_cover_data_batch(cloud_pairs, gmeta)
                for gid, detail in items.items():
                    if detail.get("gallery_id") is not None:
                        continue
                    meta = gmeta.get(gid, {})
                    detail["cover_data"] = cover_map.get(gid)
                    detail["file_size"] = detail.get("file_size") or meta.get("file_size")
                    detail["posted_at"] = detail.get("posted_at") or main._unix_to_iso(meta.get("posted"))
                    if meta.get("tags"):
                        detail["tags"] = [
                            {"namespace": ns, "name": name}
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
    return Response(
        path.read_bytes(),
        media_type=main._image_content_type(path.read_bytes()),
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

