"""Local-library reading progress and history endpoints.

The six handlers were moved out of the ``galleries`` package ``__init__``
verbatim; the package re-exports them and includes :data:`router` at the
registration position they occupied before the split, so URL paths, the
response shapes, the route resolution order (``DELETE /api/galleries/progress``
must precede ``DELETE /api/galleries/{identifier}``), the OpenAPI snapshot and
``monkeypatch.setattr(galleries, ...)`` all keep working.

Test-patched collaborators (``GalleryRepository``, ``db_error``,
``get_session``, ``resolve_session``, ``display_title``) stay on the
``galleries`` package and are resolved at call time through :func:`_gal` and
injected into :mod:`galleryvault.services.reading.progress`.

Progress endpoints never load the page list: :func:`_gallery_page_count`
resolves the gallery row and asks the repository for ``page_count(id)``, so
saving/reading progress costs one ``COUNT(*)`` instead of fetching every page
row (including manifests).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...services.reading import (
    ReadingDeps,
    clear_all_progress,
    delete_gallery_progress,
    delete_history,
    get_gallery_progress,
    get_history,
    update_gallery_progress,
)
from ..dependencies import get_session
from ..schemas import ProgressRequest
from ..state import app_state

router = APIRouter()


def _gal() -> Any:
    """Return the ``galleries`` package for runtime attribute lookup (no import cycle)."""
    from . import galleries

    return galleries


async def _gallery_page_count(
    identifier: int, session: AsyncSession | None = None
) -> tuple[Any, int]:
    """Resolve a gallery and count its pages without loading the page list."""
    gal = _gal()
    if session is None:
        if not app_state.session_factory:
            raise HTTPException(
                status_code=503, detail="Database session factory not initialized"
            )
        async with app_state.session_factory() as s:
            return await _gallery_page_count(identifier, session=s)
    try:
        repo = gal.GalleryRepository(session)
        row = await repo.get_by_id(identifier)
        if row is None:
            row = await repo.get_by_gid(identifier)
        if row is None:
            raise HTTPException(status_code=404, detail="Gallery not found")
        return row, await repo.page_count(row.id)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise gal.db_error(exc) from exc


def _deps() -> ReadingDeps:
    """Build the use-case collaborators from the package's current globals."""
    gal = _gal()
    return ReadingDeps(
        gallery_repo=gal.GalleryRepository,
        gallery_page_count=_gallery_page_count,
        display_title=gal.display_title,
    )


@router.get("/api/galleries/{identifier}/progress")
async def gallery_progress(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal().resolve_session(session, fallback_dep=_gal().get_session)
    return await get_gallery_progress(
        identifier, session=session, deps=_deps()
    )


@router.put("/api/galleries/{identifier}/progress")
async def save_gallery_progress(
    identifier: int,
    body: ProgressRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal().resolve_session(session, fallback_dep=_gal().get_session)
    return await update_gallery_progress(
        identifier, body, session=session, deps=_deps()
    )


@router.get("/api/history")
async def history(
    page: int = 1,
    page_size: int = 24,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal().resolve_session(session, fallback_dep=_gal().get_session)
    return await get_history(
        page, page_size, session=session, deps=_deps()
    )


@router.delete("/api/history", status_code=204)
async def clear_history(
    confirm: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="confirm=true is required to clear all history",
        )
    session = await _gal().resolve_session(session, fallback_dep=_gal().get_session)
    await delete_history(session=session, deps=_deps())


@router.delete("/api/galleries/progress", status_code=204)
async def clear_all_gallery_progress(
    confirm: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="confirm=true is required to clear all progress",
        )
    session = await _gal().resolve_session(session, fallback_dep=_gal().get_session)
    await clear_all_progress(session=session, deps=_deps())


@router.delete("/api/galleries/{identifier}/progress", status_code=204)
async def clear_gallery_progress(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    session = await _gal().resolve_session(session, fallback_dep=_gal().get_session)
    await delete_gallery_progress(
        identifier, session=session, deps=_deps()
    )
