"""Local gallery lists (independent of ExHentai favorites)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from ...services.list_service import ListService
from ..core.task_dispatcher import TaskDispatcher
from ..core.uow import UnitOfWork
from ..dependencies import (
    db_error,
    get_task_dispatcher,
    get_unit_of_work,
)
from ..exceptions import ConflictError, NotFoundError, ValidationError
from ..schemas import LocalListCreateRequest, LocalListItemsRequest

router = APIRouter()


def get_list_service(
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
) -> ListService:
    return ListService(uow=uow, task_dispatcher=dispatcher)


@router.get("/api/lists")
async def list_local_lists(
    service: ListService = Depends(get_list_service),  # noqa: B008
) -> dict[str, object]:
    try:
        rows = await service.list_all_lists()
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "items": [
            {
                "id": row["id"],
                "name": row["name"],
                "created_at": row.get("created_at"),
                "count": row.get("gallery_count", 0),
            }
            for row in rows
        ]
    }


@router.post("/api/lists", status_code=201)
async def create_local_list(
    body: LocalListCreateRequest,
    service: ListService = Depends(get_list_service),  # noqa: B008
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
) -> dict[str, object]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        res = await service.create_list(name)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    list_id = int(res["id"])
    dispatcher.spawn_record_task(
        "local-list-create",
        status="success",
        reason=f"list {list_id}",
        done=1,
        total=1,
    )
    return {"id": list_id, "name": res["name"], "count": 0}


@router.patch("/api/lists/{list_id}")
async def rename_local_list(
    list_id: int,
    body: LocalListCreateRequest,
    service: ListService = Depends(get_list_service),  # noqa: B008
) -> dict[str, object]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        res = await service.rename_list(list_id, name)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="list not found")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"id": res["id"], "name": res["name"]}


@router.delete("/api/lists/{list_id}")
async def delete_local_list(
    list_id: int,
    service: ListService = Depends(get_list_service),  # noqa: B008
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
) -> dict[str, object]:
    try:
        await service.delete_list(list_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="list not found")
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    dispatcher.spawn_record_task(
        "local-list-delete",
        status="success",
        reason=f"list {list_id}",
        done=1,
        total=1,
    )
    return {"deleted": True, "id": list_id}


@router.get("/api/lists/{list_id}")
async def get_local_list(
    list_id: int,
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    try:
        async with uow:
            row = await uow.lists.get(list_id)
            if row is None:
                raise HTTPException(status_code=404, detail="list not found")
            ids = await uow.lists.get_gallery_ids_for_list(list_id)
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
async def add_local_list_items(
    list_id: int,
    body: LocalListItemsRequest,
    service: ListService = Depends(get_list_service),  # noqa: B008
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
) -> dict[str, object]:
    try:
        added = await service.add_galleries_to_list(list_id, body.gallery_ids)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="list not found")
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    dispatcher.spawn_record_task(
        "local-list-add",
        status="success",
        reason=f"list {list_id}",
        done=added,
        total=len(body.gallery_ids),
    )
    return {"id": list_id, "added": added}


@router.post("/api/lists/{list_id}/items/remove")
async def remove_local_list_items(
    list_id: int,
    body: LocalListItemsRequest,
    service: ListService = Depends(get_list_service),  # noqa: B008
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
) -> dict[str, object]:
    try:
        removed = await service.remove_galleries_from_list(list_id, body.gallery_ids)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="list not found")
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    dispatcher.spawn_record_task(
        "local-list-remove",
        status="success",
        reason=f"list {list_id}",
        done=removed,
        total=len(body.gallery_ids),
    )
    return {"id": list_id, "removed": removed}


@router.get("/api/galleries/{identifier}/lists")
async def gallery_local_lists(
    identifier: int,
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    try:
        async with uow:
            row = await uow.galleries.get_by_identifier(identifier)
            if row is None:
                raise HTTPException(status_code=404, detail="Gallery not found")
            lists = await uow.lists.lists_for_gallery(row.id)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"items": [{"id": item.id, "name": item.name} for item in lists]}
