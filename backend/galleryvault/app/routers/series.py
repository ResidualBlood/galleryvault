"""Series endpoints for managing multi-work gallery groups."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Gallery
from ...db.repositories.galleries import GalleryRepository
from ...db.repositories.series import SeriesRepository
from ...db.session import safe_transaction
from ...services.series import rebuild_series_groups
from ...services.tag_translation import translated_tag
from ..core.task_dispatcher import TaskDispatcher
from ..core.uow import UnitOfWork
from ..dependencies import (
    db_error,
    display_title,
    get_session,
    get_task_dispatcher,
    get_task_manager,
    get_unit_of_work,
    resolve_session,
)

router = APIRouter()


class SeriesCreateRequest(BaseModel):
    name: str


class SeriesItemsRequest(BaseModel):
    gallery_ids: list[int] = Field(default_factory=list)
    gids: list[int] = Field(default_factory=list)


class SeriesCloudItemsRequest(BaseModel):
    gids: list[int] = Field(default_factory=list)


def _serialize_card(m: Any, tag_map: dict[int, list[tuple[str, str]]]) -> dict[str, Any]:
    if isinstance(m, dict):
        raw_tags = m.get("tags") or []
        tags = []
        for item in raw_tags:
            if isinstance(item, dict) and "namespace" in item and "name" in item:
                ns, name = str(item["namespace"]), str(item["name"])
                tags.append(
                    {
                        "namespace": ns,
                        "name": name,
                        "display": item.get("display") or translated_tag(ns, name)[1],
                    }
                )
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                ns, name = str(item[0]), str(item[1])
                tags.append(
                    {
                        "namespace": ns,
                        "name": name,
                        "display": translated_tag(ns, name)[1],
                    }
                )
        is_local = m.get("is_local", False)
        gid = m.get("gid")
        token = m.get("token")
        cover_url = (
            f"/api/favorites/cover?gid={int(gid)}&token={token}"
            if (not is_local and gid and token)
            else (m.get("cover_url") if is_local else None)
        )
        return {
            "id": m.get("id"),
            "gallery_id": m.get("gallery_id"),
            "is_local": is_local,
            "gid": gid,
            "favcat": m.get("favcat"),
            "token": token,
            "url": m.get("url"),
            "title": m.get("title", ""),
            "category": m.get("category") or "other",
            "page_count": m.get("page_count", 0),
            "cover_url": cover_url,
            "tags": tags,
        }

    is_local = getattr(m, "is_local", True)
    g_id = getattr(m, "id", None)
    gallery_id = g_id if is_local else None
    gid = getattr(m, "gid", None)
    token = getattr(m, "token", None)
    category = getattr(m, "category", None) or "other"
    page_count = getattr(m, "page_count", None) or 0
    url = getattr(m, "url", None) or (
        f"https://e-hentai.org/g/{gid}/{token}/" if gid and token else None
    )
    if is_local:
        cover_url = (
            f"/api/galleries/{g_id}/thumb/0"
            if (g_id and page_count)
            else getattr(m, "cover_url", None)
        )
    else:
        cover_url = (
            f"/api/favorites/cover?gid={int(gid)}&token={token}"
            if gid and token
            else None
        )

    tags = []
    if g_id is not None and g_id in tag_map:
        tags = [
            {
                "namespace": ns,
                "name": name,
                "display": translated_tag(ns, name)[1],
            }
            for ns, name in tag_map.get(g_id, [])
        ]

    try:
        title_str = display_title(m) if hasattr(m, "title") else getattr(m, "title", "")
    except Exception:  # noqa: BLE001
        title_str = getattr(m, "title", "") or ""

    return {
        "id": gallery_id,
        "gallery_id": gallery_id,
        "is_local": is_local,
        "gid": gid,
        "favcat": getattr(m, "favcat", None),
        "token": token,
        "url": url,
        "title": title_str,
        "category": category,
        "page_count": page_count,
        "cover_url": cover_url,
        "tags": tags,
    }


async def _resolve_repos(
    session: AsyncSession | None,
    uow: UnitOfWork | None,
) -> tuple[SeriesRepository, GalleryRepository, Any]:
    actual_session = await resolve_session(session, fallback_dep=get_session)
    repo = SeriesRepository(actual_session)
    gal_repo = GalleryRepository(actual_session)
    return repo, gal_repo, actual_session


@router.get("/api/series")
async def list_series(
    page: int = 1,
    page_size: int = 25,
    show_all: int = 0,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    is_show_all = bool(show_all)

    try:
        repo, gal_repo, _ = await _resolve_repos(session, uow)
        rows, total = await repo.list_paged(
            page=page, page_size=page_size, show_all=is_show_all
        )
        local_gallery_ids = []
        for _, _, members in rows:
            for m in members:
                if isinstance(m, Gallery):
                    local_gallery_ids.append(m.id)
                elif isinstance(m, dict) and m.get("is_local") and m.get("gallery_id"):
                    local_gallery_ids.append(m["gallery_id"])
                elif getattr(m, "id", None) is not None and getattr(m, "is_local", True):
                    local_gallery_ids.append(m.id)
        tag_map = (
            await gal_repo.tags_for_galleries(local_gallery_ids)
            if local_gallery_ids
            else {}
        )
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
                "galleries": [_serialize_card(m, tag_map) for m in members],
            }
            for s, count, members in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/series/{series_id}")
async def get_series(
    series_id: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    try:
        repo, gal_repo, _ = await _resolve_repos(session, uow)
        res = await repo.get_with_galleries(series_id)
        if res is None:
            raise HTTPException(status_code=404, detail="series not found")
        s, members = res
        local_ids = []
        for m in members:
            if isinstance(m, Gallery):
                local_ids.append(m.id)
            elif isinstance(m, dict) and m.get("is_local") and m.get("gallery_id"):
                local_ids.append(m["gallery_id"])
            elif getattr(m, "id", None) is not None and getattr(m, "is_local", True):
                local_ids.append(m.id)
        tag_map = (
            await gal_repo.tags_for_galleries(local_ids)
            if local_ids
            else {}
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    return {
        "id": s.id,
        "name": s.name,
        "match_key": s.match_key,
        "name_manual": s.name_manual,
        "count": len(members),
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "galleries": [_serialize_card(m, tag_map) for m in members],
    }


@router.post("/api/series", status_code=201)
async def create_series(
    body: SeriesCreateRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        repo, _, s = await _resolve_repos(session, uow)
        async with safe_transaction(s):
            row = await repo.create(name, match_key=None, name_manual=True)
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
async def rename_series(
    series_id: int,
    body: SeriesCreateRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        repo, _, s = await _resolve_repos(session, uow)
        async with safe_transaction(s):
            row = await repo.rename(series_id, name)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="series not found")
    return {"id": row.id, "name": row.name, "name_manual": row.name_manual}


@router.delete("/api/series/{series_id}")
async def delete_series(
    series_id: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    try:
        repo, _, s = await _resolve_repos(session, uow)
        async with safe_transaction(s):
            ok = await repo.delete_series(series_id)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="series not found")
    return {"deleted": True, "id": series_id}


@router.post("/api/series/{series_id}/items")
async def add_series_items(
    series_id: int,
    body: SeriesItemsRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    try:
        repo, _, s = await _resolve_repos(session, uow)
        async with safe_transaction(s):
            row = await repo.get(series_id)
            if row is None:
                raise HTTPException(status_code=404, detail="series not found")
            added = await repo.add_items(series_id, body.gallery_ids, source="manual")
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"id": series_id, "added": added}


@router.get("/api/series/{series_id}/cloud-candidates")
async def get_series_cloud_candidates(
    series_id: int,
    q: str | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    try:
        repo, _, _ = await _resolve_repos(session, uow)
        series = await repo.get(series_id)
        if series is None:
            raise HTTPException(status_code=404, detail="series not found")
        items = await repo.get_cloud_candidates(series_id, q=q)
        return {"items": items}
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc


@router.post("/api/series/{series_id}/cloud-items")
async def add_series_cloud_items(
    series_id: int,
    body: SeriesCloudItemsRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    try:
        repo, _, s = await _resolve_repos(session, uow)
        async with safe_transaction(s):
            row = await repo.get(series_id)
            if row is None:
                raise HTTPException(status_code=404, detail="series not found")
            res = await repo.add_cloud_items_flow(series_id, body.gids)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"id": series_id, **res}


@router.post("/api/series/{series_id}/cloud-items/remove")
async def remove_series_cloud_items(
    series_id: int,
    body: SeriesCloudItemsRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    try:
        repo, _, s = await _resolve_repos(session, uow)
        async with safe_transaction(s):
            row = await repo.get(series_id)
            if row is None:
                raise HTTPException(status_code=404, detail="series not found")
            removed = await repo.remove_cloud_items(series_id, body.gids)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"id": series_id, "removed": removed}


@router.post("/api/series/{series_id}/items/remove")
async def remove_series_items(
    series_id: int,
    body: SeriesItemsRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uow: UnitOfWork = Depends(get_unit_of_work),  # noqa: B008
) -> dict[str, object]:
    try:
        repo, _, s = await _resolve_repos(session, uow)
        async with safe_transaction(s):
            row = await repo.get(series_id)
            if row is None:
                raise HTTPException(status_code=404, detail="series not found")
            gallery_ids = list(body.gallery_ids)
            if body.gids:
                extra_ids = list(
                    (
                        await s.scalars(
                            select(Gallery.id).where(
                                Gallery.gid.in_(body.gids),
                                Gallery.trashed.is_(False),
                            )
                        )
                    ).all()
                )
                gallery_ids.extend(extra_ids)
            removed = await repo.remove_items(series_id, gallery_ids)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"id": series_id, "removed": removed}


def _resolve_dispatcher(dispatcher: Any) -> TaskDispatcher:
    if isinstance(dispatcher, TaskDispatcher):
        return dispatcher
    return get_task_dispatcher()


@router.post("/api/series/rebuild")
async def rebuild_series(
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),  # noqa: B008
) -> dict[str, object]:
    disp = _resolve_dispatcher(dispatcher)
    tm = disp.task_manager if getattr(disp, "task_manager", None) is not None else get_task_manager()
    started_at = datetime.now(UTC).isoformat()
    try:
        stats = await rebuild_series_groups()
    except Exception as exc:
        completed_at = datetime.now(UTC).isoformat()
        if tm is not None:
            tm.record_task(
                "series-rebuild",
                started_at,
                completed_at,
                "failed",
                reason=str(exc),
                done=0,
                total=0,
            )
            disp.spawn(tm.persist_history(), "persist task history")
        raise

    completed_at = datetime.now(UTC).isoformat()
    created = int(stats.get("created", 0) or 0)
    merged = int(stats.get("merged", 0) or 0)
    reason = f"created {created} groups, merged {merged} galleries"
    if tm is not None:
        tm.record_task(
            "series-rebuild",
            started_at,
            completed_at,
            "success",
            reason=reason,
            done=merged,
            total=merged,
        )
        disp.spawn(tm.persist_history(), "persist task history")
    return {"rebuilt": True, **stats}
