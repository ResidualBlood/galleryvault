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
    return render_metrics()
