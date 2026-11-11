"""Favorites mutation services (note / move / remove / add).

The HTTP layer keeps the FastAPI handler signatures, dependency resolution and
the ``_record_*_log`` helpers; this module owns the behaviour so it can be
exercised without FastAPI.

This module deliberately imports nothing from ``galleryvault.app``: repository
classes and request-layer helpers arrive through :class:`MutationDeps`.  The
router builds the deps per request from its own module globals, which keeps the
``galleryvault.app.routers.favorites.<name>`` monkeypatch targets effective.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from ..db.session import safe_transaction
from ..logging import log_extra

__all__ = ["MutationDeps", "set_favorite_note"]


@dataclass(frozen=True)
class MutationDeps:
    """Request-scoped collaborators injected by ``app/routers/favorites.py``.

    ``release_session`` and ``db_error`` live in ``galleryvault.app``; they are
    injected rather than imported so this module stays app-layer free while the
    endpoint behaviour (connection release before the cloud call, 503 mapping)
    stays the same.
    """

    favorites_repo: type
    gallery_repo: type
    delete_local: Callable[..., Any]
    record_task: Callable[..., None]
    release_session: Callable[[Any], Awaitable[None]]
    db_error: Callable[[Exception], Exception]
    logger: logging.Logger


async def set_favorite_note(
    body: Any,
    *,
    session: Any,
    eh_client_mgr: Any,
    settings: Any,
    deps: MutationDeps,
) -> dict[str, Any]:
    """Update a favorite note via ExHentai applyfav; write local only on success.

    Order is part of the contract: validate, resolve token/favcat, release the
    pooled connection, call the cloud, and only then write locally.
    """
    token = body.token
    favcat = body.favcat
    try:
        item = await deps.favorites_repo(session).item_for_gid(body.gid)
        if item is not None:
            token = token or item.token
            if favcat is None:
                favcat = item.favcat
        if not token:
            gallery = await deps.gallery_repo(session).get_by_gid(body.gid)
            if gallery is not None:
                token = gallery.token
    except SQLAlchemyError as exc:
        raise deps.db_error(exc) from exc
    if not token:
        raise HTTPException(status_code=422, detail="token is required")
    if favcat is None:
        raise HTTPException(status_code=422, detail="not in favorites")
    # Read phase finished: return the pooled connection before the cloud call.
    await deps.release_session(session)
    cloud_ok = False
    try:
        async with eh_client_mgr.client_context(settings=settings) as client:
            await client.add_favorite(body.gid, str(token), int(favcat), note=body.note)
        cloud_ok = True
    except Exception as exc:  # noqa: BLE001
        deps.logger.warning(
            "cloud favorite note failed", extra=log_extra(error=type(exc).__name__)
        )
        cloud_ok = False
    local_updated = 0
    if cloud_ok:
        try:
            async with safe_transaction(session):
                local_updated = await deps.favorites_repo(session).update_note(
                    body.gid, body.note, favcat=int(favcat)
                )
        except SQLAlchemyError as exc:
            raise deps.db_error(exc) from exc
    deps.record_task(body.gid, cloud_ok, local_updated)
    return {
        "gid": body.gid,
        "cloud_ok": cloud_ok,
        "local_updated": local_updated,
        "note": body.note if cloud_ok else None,
    }
