"""Gallery deletion endpoints: single, bulk and filter-driven deletion.

The handlers were moved out of the ``galleries`` package ``__init__`` verbatim.
The package re-exports them and includes :data:`router` after the progress
routes, where the handlers were originally registered.  Test-patched
collaborators (``GalleryRepository``, ``delete_galleries_local``, ...) stay on
the package and are resolved through :func:`_gal` at call time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ....db.repository import _chunked
from ....scanners.base import CATEGORIES
from ...dependencies import db_error, get_session
from ...params import (
    _IMAGE_QUALITY,
    _dedupe_tags,
    _parse_posted,
    _parse_tag_filter,
    _resolve_search_tokens,
)
from ...schemas import BulkDeleteRequest, FilteredDeleteRequest

router = APIRouter()


def _gal(name: str) -> Any:
    """Resolve a name from the ``galleries`` package at call time (test patch points)."""
    from .. import galleries

    return getattr(galleries, name)


@router.delete("/api/galleries/{identifier}", status_code=204)
async def delete_gallery(
    identifier: int,
    delete_files: bool = False,
    delete_all_copies: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    results: list[dict] = []
    try:
        target_id: int | None = None
        repo = _gal("GalleryRepository")(session)
        row = await repo.get_by_id(identifier)
        if row is None:
            row = await repo.get_by_gid(identifier)
        if row is not None:
            target_id = row.id

        if target_id is None:
            raise HTTPException(status_code=404, detail="Gallery not found")

        results = await _gal("delete_galleries_local")(
            [target_id], delete_files=delete_files, delete_all_copies=delete_all_copies
        )
        _gal("_record_gallery_delete_log")(results, delete_files)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    if results and results[0].get("failed_paths"):
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to delete some gallery files",
                "failed_paths": results[0]["failed_paths"],
                "deleted_paths": results[0].get("deleted_paths", []),
            },
        )


@router.post("/api/galleries/delete-bulk", status_code=200)
async def delete_galleries_bulk(
    body: BulkDeleteRequest,
) -> dict[str, object]:
    ids = body.ids or body.gallery_ids or []
    if not ids:
        raise HTTPException(status_code=422, detail="No gallery ids provided")
    results: list[dict] = []
    try:
        unique_ids = list(dict.fromkeys(ids))
        for chunk in _chunked(unique_ids):
            batch_results = await _gal("delete_galleries_local")(
                chunk,
                delete_files=body.delete_files,
                delete_all_copies=body.delete_all_copies,
            )
            results.extend(batch_results)
        _gal("_record_gallery_delete_log")(results, body.delete_files)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    deleted = sum(1 for r in results if r.get("db_removed") or r.get("trashed"))
    trashed = sum(1 for r in results if r.get("trashed"))
    failed_deletions = [p for r in results for p in r.get("failed_paths", [])]
    return {"deleted": deleted, "trashed": trashed, "failed_deletions": failed_deletions, "results": results}


async def _filtered_delete_confirmation(request: Request) -> tuple[bool, int | None]:
    """Read the optional ``confirm`` / ``match_count`` guard fields from the raw body."""
    try:
        payload = await request.json()
    except (ValueError, TypeError):
        return False, None
    if not isinstance(payload, dict):
        return False, None
    raw_count = payload.get("match_count")
    try:
        match_count = int(raw_count) if raw_count is not None else None
    except (TypeError, ValueError):
        match_count = None
    return bool(payload.get("confirm")), match_count


@router.post("/api/galleries/delete-filtered", status_code=200)
async def delete_galleries_filtered(
    body: FilteredDeleteRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    session = await _gal("resolve_session")(session, fallback_dep=_gal("get_session"))
    if body.tag_mode not in {"and", "or"} or body.tag_match not in {"exact", "fuzzy"}:
        raise HTTPException(status_code=422, detail="invalid tag_mode or tag_match")
    category = body.category or None
    exclude_favorited = False
    if category == "__not_fav__":
        exclude_favorited = True
        category = None
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="invalid category")
    if body.read_status and body.read_status not in {"all", "unread", "reading", "completed", "read"}:
        raise HTTPException(status_code=422, detail="invalid read_status")
    storage_tier = body.storage_tier
    if storage_tier and storage_tier not in {"hot", "cold"}:
        raise HTTPException(status_code=422, detail="storage_tier must be 'hot' or 'cold'")
    parsed_tags, parsed_exc_tags = _parse_tag_filter(body.tags or body.tag)
    if body.exclude_tags:
        extra_inc, extra_exc = _parse_tag_filter(body.exclude_tags)
        parsed_exc_tags.extend(extra_inc)
        parsed_exc_tags.extend(extra_exc)
    _MAX_FILTERED_DELETE = 5000
    _CONFIRM_THRESHOLD = 200
    try:
        resolved_q = body.q or ""
        order_by = body.order_by or "id_desc"
        read_status = body.read_status
        min_rating = body.min_rating
        page_min = body.min_pages
        page_max = body.max_pages
        if body.q and body.q.strip():
            auto_inc, auto_exc, keywords, changed = await _resolve_search_tokens(body.q)
            if changed:
                parsed_tags.extend(auto_inc)
                parsed_exc_tags.extend(auto_exc)
                parsed_tags = _dedupe_tags(parsed_tags)
                parsed_exc_tags = _dedupe_tags(parsed_exc_tags)
                resolved_q = keywords
        parsed_tags = _dedupe_tags(parsed_tags)
        parsed_exc_tags = _dedupe_tags(parsed_exc_tags)
        has_filters = any(
            (
                bool(resolved_q and resolved_q.strip()),
                bool(parsed_tags),
                bool(parsed_exc_tags),
                bool(category),
                exclude_favorited,
                bool(read_status and read_status != "all"),
                min_rating is not None,
                page_min is not None,
                page_max is not None,
                body.size_min is not None,
                body.size_max is not None,
                bool(body.posted_from or body.min_posted_at),
                bool(body.posted_to or body.max_posted_at),
                bool(body.uploader and body.uploader.strip()),
                bool(body.image_quality and body.image_quality in _IMAGE_QUALITY),
                body.min_local_rating is not None,
                body.list_id is not None,
                body.favorite is not None,
                body.read is not None,
                body.expunged is not None,
                bool(body.media_type),
                bool(body.storage_type),
                bool(storage_tier),
            )
        )
        if not has_filters:
            raise HTTPException(
                status_code=400,
                detail="Empty filter condition is not allowed for filtered deletion",
            )
        matching_ids: list[int] = []
        repo = _gal("GalleryRepository")(session)
        tag_id_map: dict[tuple[str | None, str], int] = {}
        if body.tag_match == "exact":
            candidates = parsed_tags + parsed_exc_tags
            if candidates and hasattr(repo, "resolve_exact_tags"):
                tag_id_map = await repo.resolve_exact_tags(candidates)
        page = 1
        while True:
            _, rows = await repo.list_page(
                page,
                500,
                q=resolved_q,
                tags=parsed_tags,
                exclude_tags=parsed_exc_tags,
                tag_mode=body.tag_mode,
                tag_match=body.tag_match,
                tag_id_map=tag_id_map,
                category=category,
                exclude_favorited=exclude_favorited,
                order_by=order_by,
                read_status=read_status,
                 min_rating=min_rating,
                 page_min=page_min,
                 page_max=page_max,
                 size_min=body.size_min,
                 size_max=body.size_max,
                 posted_from=_parse_posted(body.posted_from or body.min_posted_at),
                 posted_to=_parse_posted(body.posted_to or body.max_posted_at, upper=True),
                 uploader=body.uploader,
                 image_quality=(
                     body.image_quality
                     if body.image_quality in _IMAGE_QUALITY
                     else None
                 ),
                 min_local_rating=body.min_local_rating,
                 list_id=body.list_id,
                 favorite=body.favorite,
                 read=body.read,
                 expunged=body.expunged,
                 media_type=body.media_type,
                 storage_type=body.storage_type,
                 storage_tier=storage_tier,
             )
            if not rows:
                break
            matching_ids.extend(r.id for r in rows)
            if len(matching_ids) > _MAX_FILTERED_DELETE:
                raise HTTPException(
                    status_code=409,
                    detail=f"matched {len(matching_ids)} galleries exceeds safe limit {_MAX_FILTERED_DELETE}; refine filter or delete in batches",
                )
            if len(rows) < 500:
                break
            page += 1

        matched = len(dict.fromkeys(matching_ids))
        if matched > _CONFIRM_THRESHOLD:
            confirm, expected_count = await _filtered_delete_confirmation(request)
            if not confirm:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "CONFIRM_REQUIRED",
                        "matched": matched,
                        "threshold": _CONFIRM_THRESHOLD,
                        "message": (
                            f"matched {matched} galleries exceeds confirm threshold "
                            f"{_CONFIRM_THRESHOLD}; resend with confirm=true and "
                            f"match_count={matched}"
                        ),
                    },
                )
            if expected_count != matched:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"match_count mismatch: confirmed {expected_count}, current "
                        f"match {matched}; refresh the filter preview before deleting"
                    ),
                )

        results: list[dict] = []
        unique_ids = list(dict.fromkeys(matching_ids))
        if unique_ids:
            for chunk in _chunked(unique_ids):
                res = await _gal("delete_galleries_local")(
                    chunk, delete_files=body.delete_files, delete_all_copies=body.delete_all_copies
                )
                results.extend(res)
        _gal("_record_gallery_delete_log")(results, body.delete_files)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    deleted = sum(1 for r in results if r.get("db_removed") or r.get("trashed"))
    trashed = sum(1 for r in results if r.get("trashed"))
    failed_deletions = [p for r in results for p in r.get("failed_paths", [])]
    return {"deleted": deleted, "trashed": trashed, "matched": len(matching_ids), "failed_deletions": failed_deletions, "results": results}


def _record_gallery_delete_log(results: list[dict[str, object]], delete_files: bool) -> None:
    now = datetime.now(UTC).isoformat()
    deleted = sum(1 for r in results if r.get("db_removed") or r.get("trashed"))
    trashed = sum(1 for r in results if r.get("trashed"))
    failed = [p for r in results for p in r.get("failed_paths", [])]
    status = "failed" if failed else "success"
    mode_text = "database record + files" if delete_files else "database record only"
    if trashed:
        mode_text += f", trashed {trashed}"
    reason = f"deleted {deleted}/{len(results)} galleries ({mode_text})"
    if failed:
        reason += f", file deletion failed: {', '.join(str(p) for p in failed[:3])}"
    tm = _gal("get_task_manager")()
    tm.record_task("gallery-delete", now, now, status, reason=reason, done=deleted, total=len(results))
