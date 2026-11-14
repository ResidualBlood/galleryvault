"""Favourite duplicate review endpoints.

The handlers were moved out of ``favorites`` verbatim; ``favorites`` re-exports
them and includes this router at the position the handlers occupied, so URL
paths, response codes, exceptions and authentication are unchanged.

Test-patched collaborators (``FavoritesRepository``, ``list_groups``,
``set_status_by_key``, ``favorites_metadata``) stay on the ``favorites``
module and are resolved at call time through :func:`_fav`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ....db.session import safe_transaction
from ....metadata.sidecar import normalize_posted, normalize_tags
from ....services.favorites_worker import run_duplicates_scan
from ....services.tag_translation import translated_tag
from ...dependencies import db_error, get_session
from ...schemas import DuplicateIgnoreRequest

# Keep the pre-split logger name so log records stay attributed to the router.
logger = logging.getLogger("galleryvault.app.routers.favorites")
router = APIRouter()


def _fav() -> Any:
    """Return the ``favorites`` module for runtime attribute lookup (no cycle)."""
    from .. import favorites

    return favorites


@router.post("/api/favorites/duplicates/scan", status_code=202)
async def duplicates_scan() -> dict[str, object]:
    tm = _fav().get_task_manager()
    if tm.duplicates_state.get("running"):
        raise HTTPException(status_code=409, detail="scan already running")
    _fav().spawn_task(run_duplicates_scan(), "duplicates scan")
    return {"started": True}


@router.get("/api/favorites/duplicates/status")
async def duplicates_status(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    """Progress from the task manager, groups from ``kind='favorites'`` rows."""
    fav = _fav()
    tm = fav.get_task_manager()
    session = await fav.resolve_session(session, fallback_dep=fav.get_session)
    try:
        rows = await fav.list_groups(session, "favorites", status="open")
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    groups = [
        {
            "key": row.group_key,
            "artist": row.artist,
            "items": list((row.payload or {}).get("items") or []),
        }
        for row in rows
    ]
    # Keep the scan order the page used before the groups became persistent.
    groups.sort(key=lambda group: -len(group["items"]))
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
        "ignored": [],
    }


@router.get("/api/favorites/duplicates/ignored")
async def duplicates_ignored_list(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[dict[str, object]]:
    fav = _fav()
    session = await fav.resolve_session(session, fallback_dep=fav.get_session)
    try:
        rows = await fav.list_groups(session, "favorites", status="dismissed")
        rows.sort(
            key=lambda row: row.dismissed_at
            or row.created_at
            or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        ignores = [
            {
                "key": row.group_key,
                "title": row.title,
                "gids": list(row.member_gids or []),
            }
            for row in rows
        ]
        all_gids = [gid for entry in ignores for gid in (entry.get("gids") or [])]
        items: dict[int, dict] = {}
        if all_gids:
            items = await fav.FavoritesRepository(session).favorite_items_detail_by_gids(all_gids)
            cloud_pairs = [
                (gid, str(detail.get("token") or ""))
                for gid, detail in items.items()
                if detail.get("gallery_id") is None and detail.get("token")
            ]
            gmeta = await fav.favorites_metadata(cloud_pairs) if cloud_pairs else {}
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
                token = str(detail.get("token") or "")
                detail["cover_url"] = (
                    f"/api/favorites/cover?gid={int(gid)}&token={token}" if token else None
                )
                detail["cover_data"] = None
                detail["file_size"] = detail.get("file_size") or meta.get("file_size")
                detail["posted_at"] = detail.get("posted_at") or normalize_posted(meta.get("posted"))
                if meta.get("tags"):
                    detail["tags"] = [
                        {
                            "namespace": t["namespace"],
                            "name": t["name"],
                            "display": translated_tag(t["namespace"], t["name"])[1],
                        }
                        for t in normalize_tags(meta.get("tags", []))
                    ]
        return [
            {**entry, "items": [items.get(gid) for gid in (entry.get("gids") or []) if gid in items]}
            for entry in ignores
        ]
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc


@router.post("/api/favorites/duplicates/ignore")
async def duplicates_ignore(
    body: DuplicateIgnoreRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    fav = _fav()
    session = await fav.resolve_session(session, fallback_dep=fav.get_session)
    key = body.key.strip()
    if not key:
        raise HTTPException(status_code=422, detail="invalid key")
    try:
        async with safe_transaction(session):
            await fav.set_status_by_key(
                session,
                "favorites",
                key,
                "dismissed",
                title=body.title,
                member_gids=body.gids,
            )
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"ok": True, "key": key}


@router.delete("/api/favorites/duplicates/ignore")
@router.post("/api/favorites/duplicates/unignore")
async def duplicates_unignore(
    key: str = "",
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    fav = _fav()
    session = await fav.resolve_session(session, fallback_dep=fav.get_session)
    key = key.strip()
    if not key:
        raise HTTPException(status_code=422, detail="invalid key")
    try:
        async with safe_transaction(session):
            await fav.set_status_by_key(session, "favorites", key, "open")
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"ok": True, "key": key}
