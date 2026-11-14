"""Saved-search endpoints.

The handlers were moved out of ``settings``; the owning router includes this
sub-router at the original registration position and re-exports the handlers so
URL paths, response codes, exceptions and log records stay unchanged.

Test-patched names (``SettingsRepository``) stay on the ``settings`` module and
are resolved at call time through ``_settings()``.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.repositories.settings import patch_settings
from ...db.session import safe_transaction
from ..dependencies import db_error, get_session, resolve_session
from ..schemas import SavedSearchRequest
from ..state import app_state

# Keep the pre-split logger name so log records stay attributed to the router.
logger = logging.getLogger("galleryvault.app.routers.settings")
router = APIRouter()

_SAVED_SEARCH_MAX = 30


def _settings():
    """Return the ``settings`` module for runtime attribute lookup (no import cycle)."""
    from . import settings

    return settings


async def _user_settings(session: AsyncSession | None = None) -> dict:
    if session is not None:
        return await _settings().SettingsRepository(session).get()
    if app_state.session_factory:
        async with app_state.session_factory() as s:
            return await _settings().SettingsRepository(s).get()
    return {}


async def _locked_user_settings(session: AsyncSession) -> dict:
    """Read ``app_config.user_settings`` under a row lock (delegated to the repo)."""
    return await _settings().SettingsRepository(session).get_for_update()


def _normalize_saved_searches(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        query = item.get("query") if isinstance(item.get("query"), dict) else {}
        ident = str(item.get("id") or "").strip()
        if not name:
            continue
        out.append({"id": ident, "name": name, "query": query})
    return out[:_SAVED_SEARCH_MAX]


@router.get("/api/saved-searches")
async def saved_searches_list(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        stored = await _user_settings(session=session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("saved searches read failed", extra={"error": str(exc)})
        stored = {}
    items = _normalize_saved_searches(stored.get("saved_searches"))
    return {"items": items}


@router.post("/api/saved-searches")
async def saved_searches_add(
    body: SavedSearchRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        async with safe_transaction(session):
            stored = await _locked_user_settings(session)
            items = _normalize_saved_searches(stored.get("saved_searches"))
            if len(items) >= _SAVED_SEARCH_MAX:
                raise HTTPException(status_code=409, detail="saved search limit reached")
            entry = {"id": uuid.uuid4().hex, "name": name, "query": body.query or {}}
            items.append(entry)
            await patch_settings(_settings().SettingsRepository(session), {"saved_searches": items})
    except HTTPException:
        raise
    except Exception as exc:
        raise db_error(exc) from exc
    return entry


@router.delete("/api/saved-searches/{search_id}")
async def saved_searches_delete(
    search_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await resolve_session(session, fallback_dep=get_session)
    try:
        async with safe_transaction(session):
            stored = await _locked_user_settings(session)
            items = _normalize_saved_searches(stored.get("saved_searches"))
            next_items = [it for it in items if it.get("id") != search_id]
            if len(next_items) == len(items):
                raise HTTPException(status_code=404, detail="saved search not found")
            await patch_settings(
                _settings().SettingsRepository(session), {"saved_searches": next_items}
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise db_error(exc) from exc
    return {"deleted": True, "id": search_id}
