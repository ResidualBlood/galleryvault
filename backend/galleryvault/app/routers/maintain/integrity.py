"""Gallery integrity endpoints.

The handlers were moved out of the ``galleries`` package ``__init__`` verbatim;
``galleries`` re-exports them and includes this router at the exact position the
handlers occupied, so URL paths, response codes and route resolution order are
unchanged.

Test-patched collaborators (``get_session``, ``get_current_settings``,
``get_task_manager``, ``spawn_task``, ``GalleryRepository``) stay on the
``galleries`` package and are resolved through :func:`_gal`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import db_error, get_session
from ...schemas.gallery import GalleryIntegrityResponse

# Keep the pre-split logger name so log records stay attributed to the router.
logger = logging.getLogger("galleryvault.app.routers.galleries")
router = APIRouter()


def _gal(name: str) -> Any:
    """Resolve a name from the ``galleries`` package at call time (test patch points)."""
    from .. import galleries

    return getattr(galleries, name)


@router.get("/api/galleries/integrity", response_model=GalleryIntegrityResponse)
async def list_integrity(
    page: int = 1,
    page_size: int = 24,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")

    tm = _gal("get_task_manager")()
    integrity_state = tm.integrity_state
    extra_ids = list(integrity_state.get("corrupt_ids") or [])

    try:
        repo = _gal("GalleryRepository")(session)
        total, rows = await repo.list_integrity_issues(
            page, page_size, extra_ids=extra_ids
        )
        g_ids = [r.id for r in rows]
        tag_map = await repo.tags_for_galleries(g_ids)
        counts = {}
        if g_ids:
            if hasattr(repo, "page_counts_for_galleries"):
                counts = await repo.page_counts_for_galleries(g_ids)
            else:
                for gid in g_ids:
                    pgs = await repo.get_pages(gid)
                    counts[gid] = len(pgs)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    magic_scan_summary = {
        "running": bool(integrity_state.get("running")),
        "started_at": integrity_state.get("started_at"),
        "completed_at": integrity_state.get("completed_at"),
        "scanned": int(integrity_state.get("scanned", 0) or 0),
        "total": int(integrity_state.get("total", 0) or 0),
        "corrupt": len(extra_ids),
    }

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "magic_scan": magic_scan_summary,
        "items": [
            _gal("serialize_gallery_integrity_item")(row, tag_map, counts.get(row.id, 0))
            for row in rows
        ],
    }


@router.post("/api/galleries/integrity/scan", status_code=202)
async def trigger_integrity_scan() -> dict[str, object]:
    settings = _gal("get_current_settings")()
    if getattr(settings, "global_paused", False):
        return {"status": "paused", "detail": "Global paused: integrity scan is disabled"}
    tm = _gal("get_task_manager")()
    integrity_state = tm.integrity_state
    if not integrity_state.get("running"):
        from ....services.integrity_worker import run_integrity_magic_scan

        integrity_state["running"] = True
        integrity_state["started_at"] = datetime.now(UTC).isoformat()
        _gal("spawn_task")(run_integrity_magic_scan(), "integrity magic scan")

    corrupt_ids = list(integrity_state.get("corrupt_ids") or [])
    magic_scan_summary = {
        "running": bool(integrity_state.get("running")),
        "started_at": integrity_state.get("started_at"),
        "completed_at": integrity_state.get("completed_at"),
        "scanned": int(integrity_state.get("scanned", 0) or 0),
        "total": int(integrity_state.get("total", 0) or 0),
        "corrupt": len(corrupt_ids),
    }
    return magic_scan_summary
