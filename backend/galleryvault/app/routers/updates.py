"""
Gallery-updates endpoints: local galleries superseded by re-uploaded
(new-gid) ExHentai versions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from galleryvault.app import main
from galleryvault.db.repository import FavoritesRepository, GalleryUpdatesRepository

router = APIRouter()


class UpdateIdsRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


@router.get("/api/updates")
async def gallery_updates_list(
    page: int = 1,
    page_size: int = 24,
    state: str = "active",
) -> dict[str, Any]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    if state not in {"active", "all", "pending", "downloading", "failed", "ignored"}:
        raise HTTPException(status_code=422, detail="invalid state")
    status_filter = None
    if state == "active":
        status_filter = None  # everything except ignored
    elif state != "all":
        status_filter = state
    try:
        async with main._settings_session() as session:
            total, rows = await GalleryUpdatesRepository(session).list_page(
                page, page_size, status_filter
            )
            favcats = [r.favcat for r in rows]
            names = await FavoritesRepository(session).category_names(favcats)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    items = []
    for row in rows:
        if status_filter == "ignored":
            pass
        elif row.status == "ignored" and state != "all":
            continue
        items.append(
            {
                "id": row.id,
                "gallery_id": row.gallery_id,
                "old_gid": row.old_gid,
                "new_gid": row.new_gid,
                "title": row.title,
                "favcat": row.favcat,
                "favcat_name": names.get(row.favcat, ""),
                "status": row.status,
                "error_message": row.error_message,
                "detected_at": row.detected_at.isoformat() if row.detected_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "cover_url": f"/api/galleries/{row.gallery_id}/thumb/0",
            }
        )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "state": state,
        "items": items,
    }


@router.post("/api/updates/scan", status_code=202)
async def gallery_updates_scan() -> dict[str, Any]:
    main._spawn(main._detect_gallery_updates(), "gallery updates detect")
    return {"status": "started"}


@router.get("/api/updates/status")
async def gallery_updates_status() -> dict[str, Any]:
    counts: dict[str, int] = {}
    try:
        async with main._settings_session() as session:
            for st in ("pending", "downloading", "failed", "ignored"):
                total, _ = await GalleryUpdatesRepository(session).list_page(1, 1, st)
                counts[st] = total
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    return {
        "detecting": bool(main.gallery_updates_state["detecting"]),
        "last_detected_at": main.gallery_updates_state.get("last_detected_at"),
        "last_run": main.gallery_updates_state.get("last_run"),
        "last_error": main.gallery_updates_state.get("last_error"),
        "last_found": main.gallery_updates_state.get("found", 0),
        "counts": counts,
    }


@router.post("/api/updates/update", status_code=202)
async def gallery_updates_run(body: UpdateIdsRequest) -> dict[str, Any]:
    if not body.ids:
        raise HTTPException(status_code=422, detail="No update ids provided")
    result = await main._run_gallery_updates(body.ids)
    return {"status": "started", **result}


@router.post("/api/updates/ignore")
async def gallery_updates_ignore(body: UpdateIdsRequest) -> dict[str, Any]:
    if not body.ids:
        raise HTTPException(status_code=422, detail="No update ids provided")
    try:
        async with main._settings_session() as session, session.begin():
            ignored = await GalleryUpdatesRepository(session).mark_ignored(body.ids)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    return {"ignored": ignored}


@router.get("/api/updates/ignored")
async def gallery_updates_ignored(page: int = 1, page_size: int = 24) -> dict[str, Any]:
    return await gallery_updates_list(page, page_size, state="ignored")


@router.post("/api/updates/unignore")
async def gallery_updates_unignore(body: UpdateIdsRequest) -> dict[str, Any]:
    if not body.ids:
        raise HTTPException(status_code=422, detail="No update ids provided")
    try:
        async with main._settings_session() as session, session.begin():
            restored = await GalleryUpdatesRepository(session).unignore(body.ids)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    return {"restored": restored}
