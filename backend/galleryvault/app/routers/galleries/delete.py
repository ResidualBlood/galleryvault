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
from ....services.library.deletion import FilteredDeleteRefused, run_filtered_delete
from ....services.library.deps import LibraryDeps
from ...dependencies import db_error, get_session
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
    deps = LibraryDeps(
        repo_factory=_gal("GalleryRepository"),
        delete_local=_gal("delete_galleries_local"),
        record_delete_log=_gal("_record_gallery_delete_log"),
    )
    try:
        return await run_filtered_delete(
            deps,
            session,
            body,
            confirmation=lambda: _filtered_delete_confirmation(request),
        )
    except FilteredDeleteRefused as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc


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
