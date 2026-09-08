"""Health and metrics endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...observability import render_metrics, set_gauge
from ..dependencies import get_session, get_task_manager, resolve_session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/healthz")
async def healthz(session: AsyncSession = Depends(get_session)) -> dict[str, str]:  # noqa: B008
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        await session.execute(select(1))
    except Exception as exc:
        logger.warning("health check failed", extra={"error": type(exc).__name__})
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok"}


@router.get("/metrics")
async def metrics() -> str:
    tm = get_task_manager()
    set_gauge("gv_scan_running", 1 if tm.scan_state.get("running") else 0)
    set_gauge("gv_tag_sync_running", 1 if tm.tag_sync_state.get("running") else 0)
    set_gauge("gv_thumb_queued", int(tm.thumb_state.get("queued") or 0))
    return render_metrics()
