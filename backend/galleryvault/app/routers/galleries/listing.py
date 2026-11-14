"""Gallery collection endpoints: list, recycle views and bulk restore/purge.

The handlers were moved out of the ``galleries`` package ``__init__`` verbatim.
The package re-exports them and includes :data:`router` / :data:`bulk_router` at
the registration positions they occupied before the split.  Test-patched
collaborators (``GalleryRepository``, ``delete_galleries_local``, ...) stay on the
package and are resolved through :func:`_gal` at call time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ....db.models import Gallery
from ....db.repository import _chunked
from ....db.session import safe_transaction
from ....scanners.base import CATEGORIES
from ....services.tag_translation import translated_tag
from ...dependencies import db_error, get_session, release_session
from ...params import (
    _IMAGE_QUALITY,
    _dedupe_tags,
    _parse_posted,
    _parse_tag_filter,
    _resolve_search_tokens,
    _tags_for_galleries,
)
from ...schemas import BulkDeleteRequest
from ...schemas.gallery import GalleryExpungedResponse, GalleryListResponse, GalleryTrashResponse

router = APIRouter()
bulk_router = APIRouter()


def _gal(name: str) -> Any:
    """Resolve a name from the ``galleries`` package at call time (test patch points)."""
    from .. import galleries

    return getattr(galleries, name)


@router.get("/api/galleries", response_model=GalleryListResponse)
async def list_galleries(
    page: int = 1,
    page_size: int = 24,
    q: str | None = None,
    tags: str | None = None,
    exclude_tags: str | None = None,
    tag_mode: str = "or",
    tag_match: str = "exact",
    category: str | None = None,
    order_by: str = "id_desc",
    read_status: str | None = None,
    min_rating: float | None = None,
    page_min: int | None = None,
    page_max: int | None = None,
    size_min: int | None = None,
    size_max: int | None = None,
    posted_from: str | None = None,
    posted_to: str | None = None,
    uploader: str | None = None,
    image_quality: str | None = None,
    storage_tier: str | None = None,
    min_local_rating: int | None = Query(default=None, ge=1, le=5),
    list_id: int | None = None,
    tags_limit: int | None = Query(default=None, ge=0, le=64),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(
            status_code=422, detail="page must be >= 1 and page_size must be between 1 and 500"
        )
    if tag_mode not in {"and", "or"} or tag_match not in {"exact", "fuzzy"}:
        raise HTTPException(status_code=422, detail="invalid tag_mode or tag_match")
    if read_status and read_status not in {"all", "unread", "reading", "completed", "read"}:
        raise HTTPException(status_code=422, detail="invalid read_status")
    if image_quality:
        image_quality = image_quality.strip().lower()
        if image_quality not in _IMAGE_QUALITY:
            raise HTTPException(status_code=422, detail="invalid image_quality")
    else:
        image_quality = None
    if storage_tier and storage_tier not in {"hot", "cold"}:
        raise HTTPException(status_code=422, detail="storage_tier must be 'hot' or 'cold'")
    posted_from_dt = _parse_posted(posted_from)
    posted_to_dt = _parse_posted(posted_to, upper=True)
    if category == "":
        category = None
    exclude_favorited = False
    if category == "__not_fav__":
        exclude_favorited = True
        category = None
    elif category and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {', '.join(CATEGORIES)}")

    parsed_inc_tags, parsed_exc_tags = _parse_tag_filter(tags)
    if exclude_tags:
        extra_inc, extra_exc = _parse_tag_filter(exclude_tags)
        parsed_exc_tags.extend(extra_inc)
        parsed_exc_tags.extend(extra_exc)

    resolved_q = q or ""
    resolved = False
    if q and q.strip():
        auto_inc, auto_exc, keywords, changed = await _resolve_search_tokens(q)
        resolved = changed
        if changed:
            parsed_inc_tags.extend(auto_inc)
            parsed_exc_tags.extend(auto_exc)
            resolved_q = keywords

    parsed_inc_tags = _dedupe_tags(parsed_inc_tags)
    parsed_exc_tags = _dedupe_tags(parsed_exc_tags)
    try:
        repo_cls = _gal("GalleryRepository")
        repo = repo_cls(session)
        tag_id_map: dict[tuple[str | None, str], int] = {}
        if tag_match == "exact":
            candidates = parsed_inc_tags + parsed_exc_tags
            if candidates:
                tag_id_map = await repo.resolve_exact_tags(candidates)
        total, rows = await repo.list_page(
            page,
            page_size,
            q=resolved_q,
            tags=parsed_inc_tags if parsed_inc_tags else (),
            exclude_tags=parsed_exc_tags if parsed_exc_tags else (),
            tag_mode=tag_mode,
            tag_match=tag_match,
            tag_id_map=tag_id_map,
            category=category,
            exclude_favorited=exclude_favorited,
            order_by=order_by,
            read_status=read_status,
            min_rating=min_rating,
            page_min=page_min,
            page_max=page_max,
            size_min=size_min,
            size_max=size_max,
            posted_from=posted_from_dt,
            posted_to=posted_to_dt,
            uploader=uploader,
            image_quality=image_quality,
            storage_tier=storage_tier,
            min_local_rating=min_local_rating,
            list_id=list_id,
        )
        g_ids = [r.id for r in rows if getattr(r, "id", None)]
        tag_map = await _tags_for_galleries(repo_cls(session), g_ids, tags_limit)
        progress_map = await repo_cls(session).progress_for_galleries(g_ids)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    tag_str_parts = []
    if parsed_inc_tags:
        tag_str_parts.extend(
            f"{namespace}:{name}" if namespace else name
            for namespace, name in parsed_inc_tags
        )
    if parsed_exc_tags:
        tag_str_parts.extend(
            f"-{namespace}:{name}" if namespace else f"-{name}"
            for namespace, name in parsed_exc_tags
        )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "q": resolved_q,
        "tags": ",".join(tag_str_parts),
        "resolved": resolved,
        "tag_mode": tag_mode,
        "tag_match": tag_match,
        "order_by": order_by,
        "read_status": read_status or "all",
        "category": "__not_fav__" if exclude_favorited else (category or ""),
        "query_tags": (
            [
                {
                    "namespace": ns,
                    "name": name,
                    "display": translated_tag(ns or "misc", name)[1],
                }
                for ns, name in parsed_inc_tags
            ]
            if resolved
            else []
        ),
        "items": [
            _gal("serialize_gallery_summary")(
                row,
                tag_map,
                reading_progress=progress_map.get(
                    row.id, _gal("_g")(row, "reading_progress", None)
                ),
            )
            for row in rows
        ],
    }


gallery_list = list_galleries


@router.get("/api/galleries/trash", response_model=GalleryTrashResponse)
async def list_trash(
    page: int = 1,
    page_size: int = 24,
    tags_limit: int | None = Query(default=None, ge=0, le=64),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    try:
        total, rows = await _gal("GalleryRepository")(session).list_trashed(page, page_size)
        g_ids = [r.id for r in rows]
        tag_map = await _tags_for_galleries(_gal("GalleryRepository")(session), g_ids, tags_limit)
        progress_map = await _gal("GalleryRepository")(session).progress_for_galleries(g_ids)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            _gal("serialize_gallery_trash_item")(row, tag_map, progress_map) for row in rows
        ],
    }


@router.get("/api/galleries/expunged", response_model=GalleryExpungedResponse)
async def list_expunged(
    page: int = 1,
    page_size: int = 24,
    tags_limit: int | None = Query(default=None, ge=0, le=64),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    if page < 1 or not 1 <= page_size <= 500:
        raise HTTPException(status_code=422, detail="invalid pagination")
    try:
        total, rows = await _gal("GalleryRepository")(session).list_expunged(page, page_size)
        g_ids = [r.id for r in rows]
        tag_map = await _tags_for_galleries(_gal("GalleryRepository")(session), g_ids, tags_limit)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            _gal("serialize_gallery_expunged_item")(row, tag_map) for row in rows
        ],
    }


class ExpungedRedownloadRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


@router.post("/api/galleries/expunged/redownload", status_code=200)
async def redownload_expunged(
    body: ExpungedRedownloadRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    ids = body.ids or []
    if not ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    unique_ids = list(dict.fromkeys(ids))
    galleries: list[Gallery] = []
    try:
        repo = _gal("GalleryRepository")(session)
        for chunk in _chunked(unique_ids):
            rows = await repo.find_by_ids(chunk)
            galleries.extend(rows)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    gallery_map = {row.id: row for row in galleries}
    queued = 0
    skipped_no_gid = 0
    skipped_no_token = 0
    # Capture plain values now: releasing the session before the network phase
    # expires ORM instances, so later access to ``row.title`` would fail.
    valid_targets: list[tuple[int, str, str | None]] = []

    for gid_id in unique_ids:
        row = gallery_map.get(gid_id)
        if row is None or not row.gid:
            skipped_no_gid += 1
            continue
        token = getattr(row, "token", None)
        if not token:
            skipped_no_token += 1
            continue
        valid_targets.append((int(row.gid), str(token), row.title))

    if valid_targets:
        # Read phase finished: return the pooled connection before prepare_galleries
        # performs the EH network calls.
        await release_session(session)
        pairs = [(gid, token) for gid, token, _ in valid_targets]
        prepared_list = await _gal("prepare_galleries")(pairs)
        default_quality = _gal("get_current_settings")().download_quality or "resample"
        for (_, _, title), prepared in zip(valid_targets, prepared_list, strict=True):
            if title and not prepared.title:
                prepared.title = title
            try:
                status, _ = await _gal("_create_from_prepared")(
                    prepared,
                    mode="gallery",
                    max_pages=None,
                    quality=default_quality,
                    fallback_title=title,
                )
            except Exception:  # noqa: BLE001, S112
                continue
            if status in ("queued", "updated"):
                queued += 1

        now = datetime.now(UTC).isoformat()
        tm = _gal("get_task_manager")()
        tm.record_task(
            "download-enqueue",
            now,
            now,
            "success",
            reason=f"expunged redownload queued {queued}",
            done=queued,
            total=len(valid_targets),
        )

    return {
        "queued": queued,
        "skipped_no_gid": skipped_no_gid,
        "skipped_no_token": skipped_no_token,
    }

# ``restore``/``purge``/``random`` were registered after the integrity endpoints.
@bulk_router.post("/api/galleries/restore", status_code=200)
async def restore_galleries(
    body: BulkDeleteRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    ids = body.ids or body.gallery_ids or []
    if not ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    try:
        async with safe_transaction(session):
            restored = await _gal("GalleryRepository")(session).restore_galleries(ids)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"restored": restored}


@bulk_router.post("/api/galleries/purge", status_code=200)
async def purge_galleries(
    body: BulkDeleteRequest,
) -> dict[str, object]:
    ids = body.ids or body.gallery_ids or []
    if not ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    try:
        unique_ids = list(dict.fromkeys(ids))
        results: list[dict] = []
        for chunk in _chunked(unique_ids):
            batch_results = await _gal("delete_galleries_local")(
                chunk,
                delete_files=body.delete_files,
                delete_all_copies=body.delete_all_copies,
                trash=False,
            )
            results.extend(batch_results)
        purged = sum(1 for r in results if r.get("db_removed"))
        failed = [p for r in results for p in r.get("failed_paths", [])]
        _gal("_record_gallery_delete_log")(results, body.delete_files)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    return {"purged": purged, "failed_deletions": failed, "results": results}


@bulk_router.get("/api/galleries/random")
async def random_gallery(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    try:
        gallery_id = await _gal("GalleryRepository")(session).random_id()
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    if gallery_id is None:
        raise HTTPException(status_code=404, detail="No galleries available")
    return {"id": gallery_id}


gallery_random = random_gallery
