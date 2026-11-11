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

__all__ = ["MutationDeps", "remove_favorites", "set_favorite_note"]


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
    release_session: Callable[[Any], Awaitable[None]]
    db_error: Callable[[Exception], Exception]
    logger: logging.Logger
    # Only ``set_favorite_note`` records its own task; ``remove_favorites``
    # returns the counters so the router can call ``_record_favorites_remove_log``
    # (which is deliberately kept in the router module).
    record_task: Callable[..., None] | None = None


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
    if deps.record_task is not None:
        deps.record_task(body.gid, cloud_ok, local_updated)
    return {
        "gid": body.gid,
        "cloud_ok": cloud_ok,
        "local_updated": local_updated,
        "note": body.note if cloud_ok else None,
    }


async def remove_favorites(
    body: Any,
    *,
    session: Any,
    eh_client_mgr: Any,
    settings: Any,
    deps: MutationDeps,
) -> dict[str, Any]:
    """Remove favorites: cloud first, then a single local transaction.

    ``successful_gids`` excludes every gid the cloud did not confirm, so a
    failed gid (including a dead session that answers with a 200 login page)
    never reaches the local delete path.  ``delete_local`` is injected by the
    router so the ``routers.favorites.delete_galleries_local`` patch target
    stays effective.
    """
    if not body.gids:
        raise HTTPException(status_code=422, detail="no galleries selected")
    gids = list(dict.fromkeys(body.gids))
    cloud_failed: list[int] = []
    cloud_removed = 0
    cloud_ok = True
    try:
        async with eh_client_mgr.client_context(settings=settings) as client:
            cloud_failed = await client.remove_favorites(gids)
        cloud_removed = len(gids) - len(cloud_failed)
        cloud_ok = not cloud_failed
    except Exception as exc:  # noqa: BLE001
        cloud_ok = False
        cloud_failed = list(gids)
        deps.logger.warning(
            "cloud favorite removal failed", extra=log_extra(error=type(exc).__name__)
        )

    successful_gids = [g for g in gids if g not in set(cloud_failed)]
    local_removed = 0
    deleted_local_galleries = 0
    failed_deletions: list[str] = []
    try:
        # Cloud failures (including a dead session that returns a 200 login page)
        # remove the gid from ``successful_gids`` above, so a failed gid never
        # reaches the local delete path.  The favorite rows and the local
        # gallery/file removal share this single transaction scope.
        async with safe_transaction(session):
            if successful_gids:
                local_removed = await deps.favorites_repo(session).remove_gids(
                    successful_gids
                )

            if successful_gids and (body.delete_local or body.delete_files):
                mapping = await deps.favorites_repo(session).galleries_for_gids(
                    successful_gids
                )
                gallery_ids = [gid for gid in mapping.values() if gid is not None]

                if gallery_ids:
                    results = await deps.delete_local(
                        gallery_ids,
                        delete_files=True,
                        delete_all_copies=body.delete_all_copies,
                    )
                    deleted_local_galleries = sum(
                        1 for r in results if r.get("db_removed")
                    )
                    for r in results:
                        failed_deletions.extend(r.get("failed_paths", []))
    except SQLAlchemyError as exc:
        raise deps.db_error(exc) from exc

    return {
        "gids": gids,
        "cloud_ok": cloud_ok,
        "cloud_removed": cloud_removed,
        "cloud_failed": cloud_failed,
        "local_removed": local_removed,
        "deleted_local_galleries": deleted_local_galleries,
        "failed_deletions": failed_deletions,
    }
