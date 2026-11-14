"""Reading progress/history use-cases.

Two domains share this module because they answer the same reader question:

* the local-library endpoints (``GET/PUT /api/galleries/{identifier}/progress``,
  ``GET/DELETE /api/history`` and the progress clear endpoints) which key on
  ``galleries.id``;
* the online endpoints (``/api/eh/galleries/{gid}/{token}/progress`` and
  ``/api/eh/history``) which key on the ExHentai ``gid`` and never touch the
  local library.

Behaviour is unchanged from the pre-split router bodies: the same repository
methods are called in the same order, the local write and its history mirror
share one transaction, and ``advance_progress`` still decides whether history
is written.  Collaborators arrive through :class:`ReadingDeps` /
:class:`OnlineReadingDeps` so ``monkeypatch.setattr(galleries, ...)`` keeps
working and this layer stays independent of ``app.state``/``app.dependencies``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from ...db.session import safe_transaction

logger = logging.getLogger("galleryvault.services.reading.progress")

__all__ = [
    "OnlineReadingDeps",
    "ReadingDeps",
    "clear_all_progress",
    "delete_gallery_progress",
    "delete_history",
    "get_gallery_progress",
    "get_history",
    "get_online_progress",
    "list_online_history",
    "save_online_progress",
    "update_gallery_progress",
]


@dataclass(frozen=True)
class ReadingDeps:
    """Local-library collaborators injected by ``app/routers/reading.py``."""

    gallery_repo: type
    invoke_gallery: Callable[..., Awaitable[tuple[Any, list[Any]]]]
    display_title: Callable[[Any], str]


@dataclass(frozen=True)
class OnlineReadingDeps:
    """Online collaborators injected by ``app/routers/eh_progress.py``."""

    online_repo: type
    db_error: Callable[[Exception], Exception]


def _online_payload(row: Any) -> dict[str, Any]:
    return {
        "page": row.current_page,
        "total_pages": row.total_pages,
        "updated_at": row.updated_at,
    }


# ---------------------------------------------------------------------------
# local library
# ---------------------------------------------------------------------------


async def get_gallery_progress(
    identifier: int,
    *,
    session: Any,
    deps: ReadingDeps,
) -> dict[str, object]:
    row, pages = await deps.invoke_gallery(identifier, session=session)
    progress = await deps.gallery_repo(session).progress(row.id)
    return {
        "gallery_id": row.id,
        "current_page": progress.current_page if progress else 0,
        "total_pages": progress.total_pages if progress else len(pages),
        "updated_at": progress.updated_at if progress else None,
    }


async def update_gallery_progress(
    identifier: int,
    body: Any,
    *,
    session: Any,
    deps: ReadingDeps,
) -> dict[str, object]:
    row, pages = await deps.invoke_gallery(identifier, session=session)
    if not pages:
        raise HTTPException(status_code=400, detail="Gallery has no pages")
    current = body.current_page if body.current_page is not None else (body.page or 0)
    total_pages = body.total_pages or len(pages)
    if current < 0 or current >= len(pages):
        raise HTTPException(status_code=422, detail="current_page is outside gallery")
    async with safe_transaction(session):
        repo = deps.gallery_repo(session)
        progress, advanced = await repo.advance_progress(row.id, current, total_pages)
        if advanced:
            # History mirrors the persisted progress (same transaction), not the
            # possibly stale page from this request.
            await repo.record_history(
                row.id, progress.current_page, progress.total_pages
            )
    persisted = progress.current_page if progress else current
    return {
        "gallery_id": row.id,
        "current_page": persisted,
        "total_pages": progress.total_pages if progress else total_pages,
        "reading_progress": persisted,
    }


async def get_history(
    page: int,
    page_size: int,
    *,
    session: Any,
    deps: ReadingDeps,
) -> dict[str, object]:
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    repo = deps.gallery_repo(session)
    total, rows = await repo.history_page(page, page_size)
    galleries = {}
    if rows:
        g_ids = list({x.gallery_id for x in rows})
        found_galleries = await repo.find_by_ids(g_ids)
        galleries = {g.id: g for g in found_galleries}
    display_title = deps.display_title
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "gallery_id": x.gallery_id,
                "current_page": x.current_page,
                "total_pages": x.total_pages,
                "last_read_at": x.last_read_at,
                "title": (
                    display_title(galleries[x.gallery_id])
                    if x.gallery_id in galleries
                    else None
                ),
                "display_title": (
                    display_title(galleries[x.gallery_id])
                    if x.gallery_id in galleries
                    else None
                ),
                "raw_title": (
                    galleries[x.gallery_id].title if x.gallery_id in galleries else None
                ),
                "title_jpn": (
                    galleries[x.gallery_id].title_jpn if x.gallery_id in galleries else None
                ),
                "gid": galleries[x.gallery_id].gid if x.gallery_id in galleries else None,
                "category": (
                    galleries[x.gallery_id].category if x.gallery_id in galleries else None
                ),
                "url": f"/galleries/{x.gallery_id}",
            }
            for x in rows
        ],
    }


async def delete_history(*, session: Any, deps: ReadingDeps) -> None:
    async with safe_transaction(session):
        await deps.gallery_repo(session).clear_history()


async def clear_all_progress(*, session: Any, deps: ReadingDeps) -> None:
    async with safe_transaction(session):
        await deps.gallery_repo(session).clear_progress()


async def delete_gallery_progress(
    identifier: int,
    *,
    session: Any,
    deps: ReadingDeps,
) -> None:
    row, _ = await deps.invoke_gallery(identifier, session=session)
    async with safe_transaction(session):
        await deps.gallery_repo(session).delete_progress(row.id)


# ---------------------------------------------------------------------------
# online (ExHentai-only) galleries
# ---------------------------------------------------------------------------


async def get_online_progress(
    gid: int,
    token: str,
    *,
    session: Any,
    deps: OnlineReadingDeps,
) -> dict[str, Any] | None:
    """Return the payload, or ``None`` when absent or owned by another token."""
    try:
        row = await deps.online_repo(session).get(gid)
    except SQLAlchemyError as exc:
        raise deps.db_error(exc) from exc
    if row is None or (row.token or "").lower() != token.lower():
        return None
    return _online_payload(row)


async def save_online_progress(
    gid: int,
    token: str,
    *,
    session: Any,
    page: int,
    total_pages: int | None,
    title: str | None,
    thumb: str | None,
    deps: OnlineReadingDeps,
) -> dict[str, Any]:
    try:
        async with safe_transaction(session):
            row, _accepted = await deps.online_repo(session).save(
                gid,
                token=token,
                page=page,
                total_pages=total_pages,
                title=title,
                thumb=thumb,
            )
    except SQLAlchemyError as exc:
        raise deps.db_error(exc) from exc
    return _online_payload(row)


async def list_online_history(
    page: int,
    page_size: int,
    *,
    session: Any,
    deps: OnlineReadingDeps,
) -> dict[str, Any]:
    """Recently read online galleries, newest ``updated_at`` first."""
    try:
        rows, total = await deps.online_repo(session).history(
            (page - 1) * page_size, page_size
        )
    except SQLAlchemyError as exc:
        raise deps.db_error(exc) from exc
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                "gid": row.gid,
                "token": row.token,
                "title": row.title,
                "thumb": row.thumb,
                "page": row.current_page,
                "total_pages": row.total_pages,
                "updated_at": row.updated_at,
            }
            for row in rows
        ],
    }
