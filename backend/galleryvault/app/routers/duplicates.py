"""Duplicate-copy endpoints: list, resolve (keep a copy), dismiss, thumbnails.

A library scan persists duplicate groups into ``duplicate_records``; this router
lets the cleanup page review every physical copy of a gid and decide which one
to keep.  File deletions are only allowed for paths listed in a duplicate
record and located inside the configured scan roots.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from galleryvault.app import main
from galleryvault.db.repository import GalleryRepository
from galleryvault.scanners import registry
from galleryvault.services.ingest import GalleryIngestService
from galleryvault.services.thumbnails import ThumbnailError

router = APIRouter()

DUP_JPEG = "image/jpeg"


class DuplicateResolveRequest(BaseModel):
    path: str
    delete_others: bool = False


def _in_roots(path: Path) -> bool:
    roots = [Path(root) for root in main._scan_roots()]
    resolved = path.resolve()
    return any(resolved.is_relative_to(root) for root in roots)


async def _scan_copy(path: Path):
    scanner = registry.for_path(path)
    if scanner is None:
        raise HTTPException(status_code=422, detail=f"No scanner for {path}")
    try:
        return await run_in_threadpool(scanner.scan, path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot read copy: {exc}") from exc

@router.get("/api/scan/duplicates")
async def list_duplicates() -> dict[str, object]:
    async with main._settings_session() as session:
        groups = await GalleryRepository(session).list_duplicates()
    return {"groups": groups, "count": len(groups)}


@router.post("/api/scan/duplicates/{gid}/resolve")
async def resolve_duplicate(gid: int, body: DuplicateResolveRequest) -> dict[str, object]:
    chosen = Path(body.path)
    if not _in_roots(chosen):
        raise HTTPException(status_code=422, detail="path is outside the scan roots")
    async with main._settings_session() as session:
        groups = await GalleryRepository(session).list_duplicates()
    group = next((g for g in groups if int(g["gid"]) == gid), None)
    if group is None:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    copies = group["copies"]
    if not any(str(copy.get("path")) == str(chosen) for copy in copies):
        raise HTTPException(status_code=422, detail="path is not a copy in this group")
    # Repoint the DB row at the chosen copy (upsert by gid).
    meta = await _scan_copy(chosen)
    async with main._settings_session() as session, session.begin():
        await GalleryIngestService(session).ingest([meta])
    if body.delete_others:
        for copy in copies:
            target = Path(str(copy.get("path")))
            if target == chosen or not _in_roots(target):
                continue
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
            except OSError as exc:
                main.logger.warning(
                    "duplicate copy deletion failed",
                    extra={"path": str(target), "error": str(exc)},
                )
        # The duplicate is gone from disk; drop the record instead of waiting
        # for the next scan to clean it up.
        async with main._settings_session() as session, session.begin():
            await GalleryRepository(session).delete_duplicate(gid)
    async with main._settings_session() as session:
        refreshed = await GalleryRepository(session).list_duplicates()
    return {"groups": refreshed, "count": len(refreshed)}


@router.post("/api/scan/duplicates/{gid}/dismiss")
async def dismiss_duplicate(gid: int) -> dict[str, str]:
    async with main._settings_session() as session, session.begin():
        ok = await GalleryRepository(session).set_duplicate_status(gid, "dismissed")
    if not ok:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    return {"status": "dismissed"}


@router.post("/api/scan/duplicates/{gid}/restore")
async def restore_duplicate(gid: int) -> dict[str, str]:
    async with main._settings_session() as session, session.begin():
        ok = await GalleryRepository(session).set_duplicate_status(gid, "open")
    if not ok:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    return {"status": "open"}


@router.get("/api/scan/duplicates/thumb/{key}")
async def duplicate_thumb(key: str) -> FileResponse:
    async with main._settings_session() as session:
        groups = await GalleryRepository(session).list_duplicates()
    target: Path | None = None
    for group in groups:
        for copy in group["copies"]:
            if copy.get("key") == key:
                target = Path(str(copy.get("path")))
                break
    if target is None or not target.exists():
        raise HTTPException(status_code=404, detail="copy not found")
    service = main._thumb_service()
    cached = service.root / "dup" / key / "0.jpg"
    if not cached.is_file():
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
    return FileResponse(
        cached,
        media_type=DUP_JPEG,
        headers={"Cache-Control": "public, max-age=86400"},
    )
