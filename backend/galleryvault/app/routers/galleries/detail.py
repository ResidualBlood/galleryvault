"""Single-gallery endpoints: detail, local metadata, downloads and tag sync.

The handlers were moved out of the ``galleries`` package ``__init__`` verbatim.
:data:`router`, :data:`background_router` and :data:`sync_router` are included at
the registration positions the handlers occupied before the split.  Test-patched
collaborators stay on the package and are resolved through :func:`_gal`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ....db.models import Gallery
from ....db.repository import FavoritesRepository
from ....db.session import safe_transaction
from ....logging import log_extra
from ....services.cold_archive import archive_one, run_unarchive
from ....services.download_worker import notify_new_task
from ....services.tag_sync import GalleryGidMissing, GalleryNotFound, GalleryTokenMissing
from ....services.tag_translation import translated_tag
from ...dependencies import db_error, get_session, release_session
from ...params import _IMAGE_QUALITY
from ...schemas import DownloadOriginalRequest, GalleryLocalRequest
from ...schemas.gallery import GalleryDetail

# Keep the pre-split logger name so log records stay attributed to the router.
logger = logging.getLogger("galleryvault.app.routers.galleries")
router = APIRouter()
background_router = APIRouter()
sync_router = APIRouter()


def _gal(name: str) -> Any:
    """Resolve a name from the ``galleries`` package at call time (test patch points)."""
    from .. import galleries

    return getattr(galleries, name)


@router.get("/api/galleries/{identifier}/next")
async def gallery_next(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    try:
        next_id = await _gal("GalleryRepository")(session).next_gallery_id(identifier)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if next_id is None:
        raise HTTPException(status_code=404, detail="No next gallery")
    return {"id": next_id}


@router.get("/api/galleries/{identifier}", response_model=GalleryDetail)
async def get_gallery(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    row, pages = await _gal("_invoke_gallery")(identifier, session=session)
    tags = await _gal("_gallery_tags")(row.id, session=session)
    settings = _gal("get_current_settings")()
    return _gal("serialize_gallery_detail")(row, pages, tags, settings)


gallery_detail = get_gallery


@router.patch("/api/galleries/{identifier}/local")
async def patch_gallery_local(
    identifier: int,
    body: GalleryLocalRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    row, _ = await _gal("_invoke_gallery")(identifier, session=session)
    if body.local_rating is not None and not (1 <= body.local_rating <= 5):
        raise HTTPException(status_code=422, detail="local_rating must be 1-5")
    try:
        async with safe_transaction(session):
            gallery = await session.get(Gallery, row.id)
            if gallery is None:
                raise HTTPException(status_code=404, detail="Gallery not found")
            if "local_rating" in body.model_fields_set:
                gallery.local_rating = body.local_rating
            if "local_note" in body.model_fields_set:
                gallery.local_note = body.local_note
            if body.local_tags is not None:
                await _gal("GalleryRepository")(session).set_local_tags(gallery.id, body.local_tags)
            tags = await _gal("GalleryRepository")(session).tags_for_galleries([gallery.id])
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    tm = _gal("get_task_manager")()
    now = datetime.now(UTC).isoformat()
    tm.record_task("gallery-local", now, now, "success", reason=f"id {row.id}", done=1, total=1)
    local_tags = [
        {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
        for ns, name in tags.get(row.id, [])
        if ns == "local"
    ]
    return {
        "id": row.id,
        "local_rating": body.local_rating if "local_rating" in body.model_fields_set else row.local_rating,
        "local_note": body.local_note if "local_note" in body.model_fields_set else row.local_note,
        "local_tags": local_tags,
    }


@router.post("/api/galleries/{identifier}/download-original", status_code=202)
async def download_gallery_original(
    identifier: int,
    body: DownloadOriginalRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    """Enqueue an original-quality download for a local gallery."""
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    row, _ = await _gal("_invoke_gallery")(identifier, session=session)
    gid = int(row.gid) if row.gid else None
    token = row.token
    title = row.title
    title_jpn = getattr(row, "title_jpn", None)
    if not gid or not token:
        raise HTTPException(status_code=422, detail="Gallery has no ExHentai gid/token")
    mode = "gallery_archive" if body.archive else "gallery"
    if not body.archive:
        client = _gal("get_eh_client")()
        # Finish the read transaction before the availability check so the
        # request does not hold a pooled connection for the whole HTTP call.
        await release_session(session)
        try:
            preview = await client.fetch_gallery(
                gid, token, max_pages=1, resolve_urls=True
            )
        except Exception as exc:
            logger.warning(
                "original availability check failed",
                extra=log_extra(gid=gid, error=type(exc).__name__),
            )
            raise HTTPException(
                status_code=502, detail="ExHentai metadata request failed"
            ) from exc
        if not preview.pages or not preview.pages[0].origin_url:
            raise HTTPException(
                status_code=422, detail="No original images available for this gallery"
            )
    try:
        async with safe_transaction(session):
            task = await _gal("DownloadRepository")(session, on_new_task=notify_new_task).create(
                gid,
                token,
                title,
                mode,
                None,
                "original",
                title_jpn=title_jpn,
            )
            if task is None:
                raise HTTPException(
                    status_code=409, detail="An active download already exists for this gid"
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise db_error(exc) from exc
    return {"id": task.id, "gid": task.gid, "status": "pending"}


@router.get("/api/galleries/{identifier}/favorite")
async def gallery_favorite_status(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    try:
        row, _ = await _gal("_invoke_gallery")(identifier, session=session)
        fav_repo = FavoritesRepository(session)
        favcats = await fav_repo.favcats_for_gid(row.gid, gallery_id=row.id)
        names = await fav_repo.category_names(favcats)
        fav_item = await fav_repo.item_for_gid(row.gid) if row.gid else None
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "gid": row.gid,
        "token": row.token,
        "favorite": bool(favcats),
        "favcats": favcats,
        "favcat_names": [{"favcat": f, "name": names.get(f, "")} for f in favcats],
        "note": getattr(fav_item, "note", None) if fav_item else None,
    }


def _storage_outside_download_root(storage_path: str | None) -> bool:
    """True when an ingested copy exists outside ``download_root``.

    Redownloading such a gallery writes a second copy into the download root and
    keeps the original library directory. The client must acknowledge that with
    ``allow_copy=true`` (T2.4); otherwise the request is rejected with 409.
    """
    if not storage_path:
        return False
    try:
        resolved = Path(storage_path).resolve()
        download_root = Path(_gal("get_current_settings")().download_root).resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return False
    return not resolved.is_relative_to(download_root)


# ``redownload``/``archive``/``unarchive`` were registered after the progress routes.
@background_router.post("/api/galleries/{identifier}/redownload", status_code=202)
async def redownload_gallery(
    identifier: int,
    quality: str | None = None,
    archive: bool = False,
    allow_copy: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    if quality is not None and quality not in {"original", "resample"}:
        raise HTTPException(status_code=422, detail="quality must be 'original' or 'resample'")
    row, _ = await _gal("_invoke_gallery")(identifier, session=session)
    if not row.gid or not row.token:
        raise HTTPException(status_code=422, detail="Gallery lacks ExHentai gid/token")
    if not allow_copy and _storage_outside_download_root(getattr(row, "storage_path", None)):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "requires_copy",
                "message": (
                    "Gallery is stored outside the download root; "
                    "resend with allow_copy=true to create a second copy"
                ),
            },
        )
    if not quality:
        quality = (
            row.image_quality
            if getattr(row, "image_quality", None) in _IMAGE_QUALITY
            else (_gal("get_current_settings")().download_quality or "resample")
        )
    mode = "gallery_archive" if archive else "gallery"
    try:
        async with safe_transaction(session):
            task = await _gal("DownloadRepository")(session, on_new_task=notify_new_task).create(
                row.gid,
                row.token,
                row.title or str(row.gid),
                mode,
                quality=quality,
                title_jpn=getattr(row, "title_jpn", None),
            )
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if task is None:
        raise HTTPException(status_code=409, detail="An active download already exists for this gid")
    return {"status": "pending", "task_id": task.id, "gid": row.gid}


@background_router.post("/api/galleries/{identifier}/archive", status_code=202)
async def archive_gallery(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    """Archive a single hot gallery to cold storage (background)."""
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    row, _ = await _gal("_invoke_gallery")(identifier, session=session)
    if getattr(row, "storage_tier", "hot") == "cold":
        raise HTTPException(status_code=409, detail="Gallery is already in cold storage")
    settings = _gal("get_current_settings")()
    if not (getattr(settings, "archive_roots", None) or getattr(settings, "cold_storage_root", None)):
        raise HTTPException(status_code=422, detail="Cold storage root is not configured")
    _gal("spawn_task")(archive_one(row.id), "cold archive single")
    return {"status": "started", "id": row.id}


@background_router.post("/api/galleries/{identifier}/unarchive", status_code=202)
async def unarchive_gallery(
    identifier: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    """Move a cold gallery back to the download root (background, cancellable)."""
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    row, _ = await _gal("_invoke_gallery")(identifier, session=session)
    if getattr(row, "storage_tier", "hot") != "cold":
        raise HTTPException(status_code=409, detail="Gallery is not in cold storage")
    tm = _gal("get_task_manager")()
    if tm.unarchive_state.get("running"):
        return {"status": "running", "id": row.id}
    tm.clear_cancelled("unarchive")
    tm.unarchive_state["running"] = True
    task = _gal("spawn_task")(run_unarchive([row.id]), "cold unarchive")
    if task is None:
        tm.unarchive_state["running"] = False
        raise HTTPException(status_code=503, detail="background tasks unavailable")
    return {"status": "started", "id": row.id}


# ``sync-tags`` was registered after the delete routes.
@sync_router.post("/api/galleries/{identifier}/sync-tags")
async def sync_gallery_tags(
    identifier: int,
    redirect: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    from fastapi.responses import RedirectResponse

    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    plan: dict[str, object] | None = None
    result: object | None = None
    count = 0
    synced_at = datetime.now(UTC)
    try:
        client = _gal("get_eh_client")()
        service = _gal("TagSyncService")(client, _gal("GalleryRepository")(session))
        if callable(getattr(service, "fetch_plan", None)) and callable(
            getattr(service, "apply_plan", None)
        ):
            plan = await service.fetch_plan(identifier)
        else:
            async with safe_transaction(session):
                result = await service.sync(identifier)

        if plan is not None:
            async with safe_transaction(session):
                applier = _gal("TagSyncService")(client, _gal("GalleryRepository")(session))
                count = await applier.apply_plan(identifier, plan)
        elif result is None:
            raise HTTPException(status_code=404, detail="Gallery not found")
    except GalleryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (GalleryGidMissing, GalleryTokenMissing) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    except Exception as exc:
        logger.warning("tag sync failed", extra=log_extra(gallery_id=identifier, error=type(exc).__name__))
        raise HTTPException(status_code=502, detail="ExHentai metadata request failed") from exc
    if redirect:
        return RedirectResponse(f"/galleries/{identifier}", status_code=303)
    if result is not None:
        return {
            "id": identifier,
            "gid": getattr(result, "gid", None),
            "title": getattr(result, "title", None),
            "count": getattr(result, "count", getattr(result, "tags_added", 0)),
            "tags_added": getattr(result, "tags_added", getattr(result, "count", 0)),
            "synced_at": getattr(result, "synced_at", None),
            "source": getattr(result, "source", None),
        }
    return {
        "id": identifier,
        "gid": plan.get("gid") if plan else None,
        "title": plan.get("title") if plan else None,
        "count": count,
        "tags_added": count,
        "synced_at": synced_at,
        "source": plan.get("source") if plan else None,
    }
