"""Duplicate-copy endpoints: list, resolve (keep a copy), dismiss, thumbnails."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ...db.repository import FavoritesRepository, GalleryRepository
from ...scanners import registry
from ...services.deletion import in_scan_roots
from ...services.ingest import GalleryIngestService
from ...services.tag_translation import translated_tag
from ...services.thumbnails import ThumbnailError, ThumbnailService
from ..dependencies import get_current_settings, get_session, resolve_display_title
from ..state import app_state

logger = logging.getLogger(__name__)
router = APIRouter()
_cross_gid_lock = asyncio.Lock()

DUP_JPEG = "image/jpeg"


class DuplicateResolveRequest(BaseModel):
    path: str
    delete_others: bool = False


def _scan_roots() -> list[str]:
    settings = get_current_settings()
    roots = list(settings.library_roots)
    if settings.download_root and settings.download_root not in roots:
        roots.append(settings.download_root)
    return roots


def _in_roots(path: Path) -> bool:
    return in_scan_roots(path, _scan_roots())


def _get_thumb_service() -> ThumbnailService:
    if app_state.thumbnail_service is not None:
        return app_state.thumbnail_service
    settings = get_current_settings()
    service = ThumbnailService(settings.thumbnail_cache_dir)
    app_state.thumbnail_service = service
    return service


async def _scan_copy(path: Path) -> Any:
    scanner = registry.for_path(path)
    if scanner is None:
        raise HTTPException(status_code=422, detail=f"No scanner for {path}")
    try:
        return await run_in_threadpool(scanner.scan, path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot read copy: {exc}") from exc


@router.get("/api/scan/duplicates")
async def list_duplicates() -> dict[str, object]:
    async for session in get_session():
        groups = await GalleryRepository(session).list_duplicates()
        break
    for group in groups:
        for copy in group.get("copies") or []:
            directory = str(Path(str(copy.get("path") or "")).name)
            copy["display_title"] = (
                resolve_display_title(
                    copy.get("title"), copy.get("title_jpn"), directory
                )
                or copy.get("title")
                or str(group.get("gid") or "")
            )
            copy["tags"] = [
                {
                    "namespace": tag.get("namespace"),
                    "name": tag.get("name"),
                    "display": translated_tag(tag.get("namespace"), tag.get("name"))[1],
                }
                for tag in (copy.get("tags") or [])
            ]
    return {"groups": groups, "count": len(groups)}


@router.post("/api/scan/duplicates/{gid}/resolve")
async def resolve_duplicate(gid: int, body: DuplicateResolveRequest) -> dict[str, object]:
    chosen = Path(body.path)
    if not _in_roots(chosen):
        raise HTTPException(status_code=422, detail="path is outside the scan roots")
    async for session in get_session():
        groups = await GalleryRepository(session).list_duplicates()
        break
    group = next((g for g in groups if int(g["gid"]) == gid), None)
    if group is None:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    copies = group["copies"]
    if not any(str(copy.get("path")) == str(chosen) for copy in copies):
        raise HTTPException(status_code=422, detail="path is not a copy in this group")

    meta = await _scan_copy(chosen)
    async for session in get_session():
        async with session.begin():
            await GalleryIngestService(session).ingest([meta])
        break

    if body.delete_others:

        def _delete_path(path: Path) -> None:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)

        for copy in copies:
            target = Path(str(copy.get("path")))
            if target == chosen or not _in_roots(target):
                continue
            try:
                await run_in_threadpool(_delete_path, target)
            except OSError as exc:
                logger.warning(
                    "duplicate copy deletion failed",
                    extra={"path": str(target), "error": str(exc)},
                )
        async for session in get_session():
            async with session.begin():
                await GalleryRepository(session).delete_duplicate(gid)
            break

    async for session in get_session():
        refreshed = await GalleryRepository(session).list_duplicates()
        break
    return {"groups": refreshed, "count": len(refreshed)}


@router.post("/api/scan/duplicates/{gid}/dismiss")
async def dismiss_duplicate(gid: int) -> dict[str, str]:
    async for session in get_session():
        async with session.begin():
            ok = await GalleryRepository(session).set_duplicate_status(gid, "dismissed")
        break
    if not ok:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    return {"status": "dismissed"}


@router.post("/api/scan/duplicates/{gid}/restore")
async def restore_duplicate(gid: int) -> dict[str, str]:
    async for session in get_session():
        async with session.begin():
            ok = await GalleryRepository(session).set_duplicate_status(gid, "open")
        break
    if not ok:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    return {"status": "open"}


@router.get("/api/scan/duplicates/thumb/{key}")
async def duplicate_thumb(key: str) -> FileResponse:
    if not key or ".." in key or "/" in key or "\\" in key or Path(key).is_absolute():
        raise HTTPException(status_code=404, detail="copy not found")

    service = _get_thumb_service()
    dup_root = (service.root / "dup").resolve()
    try:
        candidate = (service.root / "dup" / key / "0.jpg").resolve()
        if not candidate.is_relative_to(dup_root):
            raise HTTPException(status_code=404, detail="copy not found")
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="copy not found")

    cached = candidate
    if not cached.is_file():
        async for session in get_session():
            groups = await GalleryRepository(session).list_duplicates()
            break
        target: Path | None = None
        for group in groups:
            for copy in group.get("copies") or []:
                if copy.get("key") == key:
                    target = Path(str(copy.get("path") or ""))
                    break
        if target is None or not target.exists():
            raise HTTPException(status_code=404, detail="copy not found")
        meta = await _scan_copy(target)
        if not meta.pages:
            raise HTTPException(status_code=422, detail="copy has no pages")
        scanner = registry.for_path(target)
        if scanner is None:
            raise HTTPException(status_code=422, detail=f"No scanner for {target}")
        stream = await run_in_threadpool(scanner.open_page, meta, meta.pages[0])
        try:
            data = await run_in_threadpool(stream.read)
        finally:
            try:
                stream.close()
            except OSError:
                pass
        try:
            cached = await run_in_threadpool(service.get_or_create_dup, key, data)
        except ThumbnailError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        resolved_cached = cached.resolve()
        if not resolved_cached.is_relative_to(dup_root) or not resolved_cached.is_file():
            raise HTTPException(status_code=404, detail="copy not found")
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="copy not found")

    return FileResponse(
        resolved_cached,
        media_type=DUP_JPEG,
        headers={"Cache-Control": "public, max-age=86400"},
    )


def _serialize_cross_gid_group(
    group: dict[str, Any],
) -> dict[str, Any]:
    items = []
    for it in group.get("items") or []:
        it_copy = dict(it)
        it_copy.pop("legacy_keys", None)
        storage_path = it_copy.get("storage_path")
        fallback = str(Path(storage_path).name) if storage_path else ""
        it_copy["display_title"] = (
            resolve_display_title(
                it_copy.get("title"), it_copy.get("title_jpn"), fallback
            )
            or it_copy.get("title")
            or (f"gid {it_copy.get('gid')}" if it_copy.get("gid") is not None else "")
        )
        if (
            it_copy.get("gallery_id") is None
            and it_copy.get("gid") is not None
            and it_copy.get("token")
            and not it_copy.get("cover_url")
        ):
            it_copy["cover_url"] = (
                f"/api/favorites/cover?gid={int(it_copy['gid'])}&token={it_copy['token']}"
            )
        items.append(it_copy)
    return {
        "key": group.get("key"),
        "artist": group.get("artist"),
        "items": items,
    }


@router.get("/api/library/duplicates/cross-gid")
async def get_cross_gid_duplicates() -> dict[str, object]:
    from ...services.duplicates import duplicate_group_is_ignored

    raw_groups = app_state.cross_gid_duplicates
    if raw_groups is None:
        return {"ready": False, "count": 0, "groups": []}

    session_factory = app_state.session_factory
    if session_factory:
        async with session_factory() as session:
            fav_repo = FavoritesRepository(session)
            ignored_keys = await fav_repo.ignored_duplicate_keys()
            ignored = await fav_repo.ignored_duplicates()
            ignored_gid_sets = [
                set(r.get("gids") or []) for r in ignored if r.get("gids")
            ]
    else:
        ignored_keys, ignored_gid_sets = set(), []

    filtered: list[dict[str, Any]] = []
    for g in raw_groups:
        if duplicate_group_is_ignored(g, ignored_keys, ignored_gid_sets):
            continue
        filtered.append(_serialize_cross_gid_group(g))

    return {"ready": True, "count": len(filtered), "groups": filtered}


@router.post("/api/library/duplicates/cross-gid/refresh")
async def refresh_cross_gid_duplicates() -> dict[str, object]:
    from ...services.duplicates import scan_library_cross_gid_duplicates

    session_factory = app_state.session_factory
    if not session_factory:
        raise HTTPException(status_code=503, detail="Database not available")

    if _cross_gid_lock.locked():
        raise HTTPException(status_code=409, detail="Cross-GID scan already running")

    async with _cross_gid_lock:
        await scan_library_cross_gid_duplicates(session_factory)
    return await get_cross_gid_duplicates()

