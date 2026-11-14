"""Reading progress and history for online galleries that are not in the library.

These endpoints never talk to ExHentai: they only persist the page counter the
browser reader already knows. ``GET`` is fetched separately after the detail
call (the detail response deliberately carries no progress) and a missing row is
a plain ``404`` so the reader can start from page 1 without a special case.

Resolved page-image URLs from ``.../pages/{n}/resolve`` are short-lived and
host-allowlisted per request; storing them here would leak expiring links into
the history, so the only URL kept is the gallery thumbnail from EH metadata and
it is accepted only for the EH thumbnail host.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ...db.repositories.online_progress import OnlineProgressRepository
from ...services.reading import (
    OnlineReadingDeps,
    get_online_progress,
    list_online_history,
    save_online_progress,
)
from ..dependencies import db_error, get_session, resolve_session
from .eh_online import _validate_gid, _validate_token

router = APIRouter()

_MAX_PAGE_SIZE = 100
_MAX_TITLE_LEN = 500
_MAX_THUMB_LEN = 2048
_THUMB_HOSTS = ("ehgt.org", "e-hentai.org", "exhentai.org")


class OnlineProgressRequest(BaseModel):
    """``PUT`` body: 1-based ``page`` plus optional display metadata."""

    page: int = Field(ge=1)
    total_pages: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None)
    thumb: str | None = Field(default=None)

    @field_validator("title", "thumb")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


def _clean_thumb(url: str | None) -> str | None:
    """Accept only EH-hosted thumbnail URLs (never a resolved page image).

    Display metadata must never fail a progress save, so an oversized URL is
    dropped instead of rejected; anything pointing at a non-EH host is a
    client bug and gets an explicit 422.
    """
    if url is None or len(url) > _MAX_THUMB_LEN:
        return None
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not any(
        host == allowed or host.endswith(f".{allowed}") for allowed in _THUMB_HOSTS
    ):
        raise HTTPException(status_code=422, detail="thumb host is not allowed")
    return url


def _deps() -> OnlineReadingDeps:
    """Collaborators for the extracted online reading use-cases."""
    return OnlineReadingDeps(
        online_repo=OnlineProgressRepository,
        db_error=db_error,
    )


@router.get("/api/eh/galleries/{gid}/{token}/progress")
async def eh_online_progress(
    gid: int,
    token: str,
    session: Any = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    gid = _validate_gid(gid)
    token = _validate_token(token)
    actual_session = await resolve_session(session)
    payload = await get_online_progress(
        gid, token, session=actual_session, deps=_deps()
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="No online reading progress")
    return payload


@router.put("/api/eh/galleries/{gid}/{token}/progress")
async def save_eh_online_progress(
    gid: int,
    token: str,
    body: OnlineProgressRequest,
    session: Any = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    gid = _validate_gid(gid)
    token = _validate_token(token)
    if body.total_pages is not None and body.page > body.total_pages:
        raise HTTPException(status_code=422, detail="page is outside total_pages")
    thumb = _clean_thumb(body.thumb)
    title = body.title[:_MAX_TITLE_LEN] if body.title else None
    actual_session = await resolve_session(session)
    return await save_online_progress(
        gid,
        token,
        session=actual_session,
        page=body.page,
        total_pages=body.total_pages,
        title=title,
        thumb=thumb,
        deps=_deps(),
    )


@router.get("/api/eh/history")
async def eh_online_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=_MAX_PAGE_SIZE),
    session: Any = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    """Recently read online galleries, newest ``updated_at`` first."""
    actual_session = await resolve_session(session)
    return await list_online_history(
        page, page_size, session=actual_session, deps=_deps()
    )
