"""Local gallery lists (independent of ExHentai favorites)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from ...db.repository import LocalListRepository
from ..dependencies import db_error, get_session, get_task_manager, spawn_task
from ..schemas import LocalListCreateRequest, LocalListItemsRequest

router = APIRouter()


def _record_list_log(action: str, list_id: int, done: int, total: int) -> None:
    now = datetime.now(UTC).isoformat()
    tm = get_task_manager()
    tm.record_task(
        f"local-list-{action}",
        now,
        now,
        "success",
        reason=f"list {list_id}",
        done=done,
        total=total,
    )
    spawn_task(tm.persist_history(), "persist task history")


@router.get("/api/lists")
async def list_local_lists() -> dict[str, object]:
    try:
        async for session in get_session():
            rows = await LocalListRepository(session).list_all()
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "count": count,
            }
            for row, count in rows
        ]
    }


@router.post("/api/lists", status_code=201)
async def create_local_list(body: LocalListCreateRequest) -> dict[str, object]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        async for session in get_session():
            async with session.begin():
                row = await LocalListRepository(session).create(name)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    _record_list_log("create", row.id, 1, 1)
    return {"id": row.id, "name": row.name, "count": 0}


@router.patch("/api/lists/{list_id}")
async def rename_local_list(list_id: int, body: LocalListCreateRequest) -> dict[str, object]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        async for session in get_session():
            async with session.begin():
                row = await LocalListRepository(session).rename(list_id, name)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="list not found")
    return {"id": row.id, "name": row.name}


@router.delete("/api/lists/{list_id}")
async def delete_local_list(list_id: int) -> dict[str, object]:
    try:
        async for session in get_session():
            async with session.begin():
                ok = await LocalListRepository(session).delete_list(list_id)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="list not found")
    _record_list_log("delete", list_id, 1, 1)
    return {"deleted": True, "id": list_id}


@router.get("/api/lists/{list_id}")
async def get_local_list(list_id: int) -> dict[str, object]:
    from sqlalchemy import select

    from ...db.models import LocalListItem

    try:
        async for session in get_session():
            repo = LocalListRepository(session)
            row = await repo.get(list_id)
            if row is None:
                raise HTTPException(status_code=404, detail="list not found")
            ids = (
                await session.scalars(
                    select(LocalListItem.gallery_id).where(LocalListItem.list_id == list_id)
                )
            ).all()
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "id": row.id,
        "name": row.name,
        "gallery_ids": [int(gid) for gid in ids],
        "count": len(ids),
    }


@router.post("/api/lists/{list_id}/items")
async def add_local_list_items(list_id: int, body: LocalListItemsRequest) -> dict[str, object]:
    try:
        async for session in get_session():
            async with session.begin():
                repo = LocalListRepository(session)
                row = await repo.get(list_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="list not found")
                added = await repo.add_items(list_id, body.gallery_ids)
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    _record_list_log("add", list_id, added, len(body.gallery_ids))
    return {"id": list_id, "added": added}


@router.post("/api/lists/{list_id}/items/remove")
async def remove_local_list_items(list_id: int, body: LocalListItemsRequest) -> dict[str, object]:
    try:
        async for session in get_session():
            async with session.begin():
                repo = LocalListRepository(session)
                row = await repo.get(list_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="list not found")
                removed = await repo.remove_items(list_id, body.gallery_ids)
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    _record_list_log("remove", list_id, removed, len(body.gallery_ids))
    return {"id": list_id, "removed": removed}


@router.get("/api/galleries/{identifier}/lists")
async def gallery_local_lists(identifier: int) -> dict[str, object]:
    from sqlalchemy import select

    from ...db.models import Gallery

    try:
        async for session in get_session():
            row = await session.scalar(select(Gallery).where(Gallery.id == identifier))
            if row is None:
                row = await session.scalar(select(Gallery).where(Gallery.gid == identifier))
            if row is None:
                raise HTTPException(status_code=404, detail="Gallery not found")
            lists = await LocalListRepository(session).lists_for_gallery(row.id)
            break
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"items": [{"id": item.id, "name": item.name} for item in lists]}
