"""Local-library reading progress and history endpoints.

The six handlers were moved out of the ``galleries`` package ``__init__``
verbatim; the package re-exports them and includes :data:`router` at the
registration position they occupied before the split, so URL paths, the
response shapes, the route resolution order (``DELETE /api/galleries/progress``
must precede ``DELETE /api/galleries/{identifier}``), the OpenAPI snapshot and
``monkeypatch.setattr(galleries, ...)`` all keep working.

Test-patched collaborators (``GalleryRepository``, ``_invoke_gallery``,
``get_session``, ``resolve_session``, ``display_title``) stay on the
``galleries`` package and are resolved at call time through :func:`_gal` and
injected into :mod:`galleryvault.services.reading.progress`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...services.reading import progress as reading_progress
from ..dependencies import get_session
from ..schemas import ProgressRequest

router = APIRouter()


def _gal() -> Any:
    """Return the ``galleries`` package for runtime attribute lookup (no import cycle)."""
    from . import galleries

    return galleries


def _deps() -> reading_progress.ReadingDeps:
    """Build the use-case collaborators from the package's current globals."""
    gal = _gal()
    return reading_progress.ReadingDeps(
        gallery_repo=gal.GalleryRepository,
        invoke_gallery=gal._invoke_gallery,
        display_title=gal.display_title,
    )


@router.get("/api/galleries/{identifier}/progress")
async def gallery_progress(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal().resolve_session(session, fallback_dep=_gal().get_session)
    return await reading_progress.get_gallery_progress(
        identifier, session=session, deps=_deps()
    )


@router.put("/api/galleries/{identifier}/progress")
async def save_gallery_progress(
    identifier: int,
    body: ProgressRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal().resolve_session(session, fallback_dep=_gal().get_session)
    return await reading_progress.update_gallery_progress(
        identifier, body, session=session, deps=_deps()
    )


@router.get("/api/history")
async def history(
    page: int = 1,
    page_size: int = 24,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal().resolve_session(session, fallback_dep=_gal().get_session)
    return await reading_progress.get_history(
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
    await reading_progress.delete_history(session=session, deps=_deps())


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
    await reading_progress.clear_all_progress(session=session, deps=_deps())


@router.delete("/api/galleries/{identifier}/progress", status_code=204)
async def clear_gallery_progress(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    session = await _gal().resolve_session(session, fallback_dep=_gal().get_session)
    await reading_progress.delete_gallery_progress(
        identifier, session=session, deps=_deps()
    )
