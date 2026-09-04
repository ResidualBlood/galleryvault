"""Series endpoints for managing multi-work gallery groups."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from ...db.models import Gallery
from ...db.repositories.galleries import GalleryRepository
from ...db.repositories.series import SeriesRepository
from ...services.series import rebuild_series_groups
from ...services.tag_translation import translated_tag
from ..dependencies import db_error, display_title, get_session, get_task_manager, spawn_task

router = APIRouter()


class SeriesCreateRequest(BaseModel):
    name: str


class SeriesItemsRequest(BaseModel):
    gallery_ids: list[int] = Field(default_factory=list)


def _serialize_card(g: Gallery, tag_map: dict[int, list[tuple[str, str]]]) -> dict[str, Any]:
    return {
        "id": g.id,
        "gid": g.gid,
        "token": g.token,
        "title": display_title(g),
        "category": g.category or "other",
        "page_count": g.page_count or 0,
        "cover_url": f"/api/galleries/{g.id}/thumb/0" if g.page_count else None,
        "tags": [
            {
                "namespace": ns,
                "name": name,
                "display": translated_tag(ns, name)[1],
            }
            for ns, name in tag_map.get(g.id, [])
        ],
    }


@router.get("/api/series")
async def list_series() -> dict[str, object]:
    try:
        async for session in get_session():
            repo = SeriesRepository(session)
            rows = await repo.list_all()
            all_gids = [g.id for _, _, galleries in rows for g in galleries]
            tag_map = (
                await GalleryRepository(session).tags_for_galleries(all_gids)
                if all_gids
                else {}
            )
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    return {
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "match_key": s.match_key,
                "name_manual": s.name_manual,
                "count": count,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "galleries": [_serialize_card(g, tag_map) for g in galleries],
            }
            for s, count, galleries in rows
        ]
    }


@router.get("/api/series/{series_id}")
async def get_series(series_id: int) -> dict[str, object]:
    try:
        async for session in get_session():
            repo = SeriesRepository(session)
            res = await repo.get_with_galleries(series_id)
            if res is None:
                raise HTTPException(status_code=404, detail="series not found")
            s, galleries = res
            gids = [g.id for g in galleries]
            tag_map = (
                await GalleryRepository(session).tags_for_galleries(gids)
                if gids
                else {}
            )
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    return {
        "id": s.id,
        "name": s.name,
        "match_key": s.match_key,
        "name_manual": s.name_manual,
        "count": len(galleries),
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "galleries": [_serialize_card(g, tag_map) for g in galleries],
    }


@router.post("/api/series", status_code=201)
async def create_series(body: SeriesCreateRequest) -> dict[str, object]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        async for session in get_session():
            async with session.begin():
                row = await SeriesRepository(session).create(name, match_key=None, name_manual=True)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "id": row.id,
        "name": row.name,
        "match_key": row.match_key,
        "name_manual": row.name_manual,
        "count": 0,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "galleries": [],
    }


@router.patch("/api/series/{series_id}")
async def rename_series(series_id: int, body: SeriesCreateRequest) -> dict[str, object]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        async for session in get_session():
            async with session.begin():
                row = await SeriesRepository(session).rename(series_id, name)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="series not found")
    return {"id": row.id, "name": row.name, "name_manual": row.name_manual}


@router.delete("/api/series/{series_id}")
async def delete_series(series_id: int) -> dict[str, object]:
    try:
        async for session in get_session():
            async with session.begin():
                ok = await SeriesRepository(session).delete_series(series_id)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="series not found")
    return {"deleted": True, "id": series_id}


@router.post("/api/series/{series_id}/items")
async def add_series_items(series_id: int, body: SeriesItemsRequest) -> dict[str, object]:
    try:
        async for session in get_session():
            async with session.begin():
                repo = SeriesRepository(session)
                row = await repo.get(series_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="series not found")
                added = await repo.add_items(series_id, body.gallery_ids, source="manual")
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"id": series_id, "added": added}


@router.post("/api/series/{series_id}/items/remove")
async def remove_series_items(series_id: int, body: SeriesItemsRequest) -> dict[str, object]:
    try:
        async for session in get_session():
            async with session.begin():
                repo = SeriesRepository(session)
                row = await repo.get(series_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="series not found")
                removed = await repo.remove_items(series_id, body.gallery_ids)
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"id": series_id, "removed": removed}


@router.post("/api/series/rebuild")
async def rebuild_series() -> dict[str, object]:
    started_at = datetime.now(UTC).isoformat()
    tm = get_task_manager()
    try:
        stats = await rebuild_series_groups()
    except Exception as exc:
        completed_at = datetime.now(UTC).isoformat()
        tm.record_task(
            "series-rebuild",
            started_at,
            completed_at,
            "failed",
            reason=str(exc),
            done=0,
            total=0,
        )
        spawn_task(tm.persist_history(), "persist task history")
        raise

    completed_at = datetime.now(UTC).isoformat()
    created = int(stats.get("created", 0) or 0)
    merged = int(stats.get("merged", 0) or 0)
    reason = f"created {created} groups, merged {merged} galleries"
    tm.record_task(
        "series-rebuild",
        started_at,
        completed_at,
        "success",
        reason=reason,
        done=merged,
        total=merged,
    )
    spawn_task(tm.persist_history(), "persist task history")
    return {"rebuilt": True, **stats}
