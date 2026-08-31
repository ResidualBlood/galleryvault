"""Health and metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from galleryvault.app import main
from galleryvault.observability import render_metrics

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    try:
        async with main._settings_session() as session:
            await session.execute(select(1))
    except Exception as exc:  # report unavailability, not the cause
        main.logger.warning("health check failed", extra={"error": type(exc).__name__})
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok"}


@router.get("/metrics")
async def metrics() -> str:
    from galleryvault.observability import set_gauge

    set_gauge("gv_scan_running", 1 if main.scan_state.get("running") else 0)
    set_gauge("gv_tag_sync_running", 1 if main.tag_sync_state.get("running") else 0)
    set_gauge("gv_thumb_queued", int(main.thumb_state.get("queued") or 0))
    return render_metrics()
