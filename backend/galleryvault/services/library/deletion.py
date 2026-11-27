"""Filter-driven gallery deletion use-case.

Extracted from ``app/routers/galleries/delete.py`` (T9.2c).  The router keeps
FastAPI request parsing (including the ``confirm``/``match_count`` guard body)
and injects ``delete_galleries_local`` / ``_record_gallery_delete_log`` through
:class:`~.deps.LibraryDeps`, so ``monkeypatch.setattr(galleries, ...)`` keeps
working.

This module only owns the *filtered* delete flow; the local copy deletion
(`${services.deletion}`'s ``delete_galleries_local``) stays where it is until
the B11 library split.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ...app.params import (
    _IMAGE_QUALITY,
    _dedupe_tags,
    _parse_posted,
    _parse_tag_filter,
    _resolve_search_tokens,
)
from ...db.repository import _chunked
from ...scanners.base import CATEGORIES
from .deps import LibraryDeps

__all__ = ["FilteredDeleteRefused", "run_filtered_delete"]

_MAX_FILTERED_DELETE = 5000
_CONFIRM_THRESHOLD = 200

ConfirmationReader = Callable[[], Awaitable[tuple[bool, int | None]]]


class FilteredDeleteRefused(Exception):
    """A filtered delete the use-case refuses; the router maps it to HTTP."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


def _refuse(status_code: int, detail: Any) -> None:
    raise FilteredDeleteRefused(status_code, detail)


async def run_filtered_delete(
    deps: LibraryDeps,
    session: Any,
    body: Any,
    *,
    confirmation: ConfirmationReader | None = None,
) -> dict[str, object]:
    """Resolve the filter, page every match and delete it in chunks."""
    if body.tag_mode not in {"and", "or"} or body.tag_match not in {"exact", "fuzzy"}:
        _refuse(422, "invalid tag_mode or tag_match")
    category = body.category or None
    exclude_favorited = False
    if category == "__not_fav__":
        exclude_favorited = True
        category = None
    if category is not None and category not in CATEGORIES:
        _refuse(422, "invalid category")
    if body.read_status and body.read_status not in {
        "all",
        "unread",
        "reading",
        "completed",
        "read",
    }:
        _refuse(422, "invalid read_status")
    storage_tier = body.storage_tier
    if storage_tier and storage_tier not in {"hot", "cold"}:
        _refuse(422, "storage_tier must be 'hot' or 'cold'")
    parsed_tags, parsed_exc_tags = _parse_tag_filter(body.tags or body.tag)
    if body.exclude_tags:
        extra_inc, extra_exc = _parse_tag_filter(body.exclude_tags)
        parsed_exc_tags.extend(extra_inc)
        parsed_exc_tags.extend(extra_exc)

    repo = deps.repo_factory(session)
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
        _refuse(400, "Empty filter condition is not allowed for filtered deletion")

    matching_ids: list[int] = []
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
            image_quality=(body.image_quality if body.image_quality in _IMAGE_QUALITY else None),
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
            _refuse(
                409,
                f"matched {len(matching_ids)} galleries exceeds safe limit "
                f"{_MAX_FILTERED_DELETE}; refine filter or delete in batches",
            )
        if len(rows) < 500:
            break
        page += 1

    matched = len(dict.fromkeys(matching_ids))
    if matched > _CONFIRM_THRESHOLD:
        confirm, expected_count = (
            await confirmation() if confirmation is not None else (False, None)
        )
        if not confirm:
            _refuse(
                409,
                {
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
            _refuse(
                409,
                f"match_count mismatch: confirmed {expected_count}, current "
                f"match {matched}; refresh the filter preview before deleting",
            )

    if deps.delete_local is None or deps.record_delete_log is None:
        raise RuntimeError("deletion deps are missing collaborators")
    results: list[dict] = []
    unique_ids = list(dict.fromkeys(matching_ids))
    if unique_ids:
        for chunk in _chunked(unique_ids):
            res = await deps.delete_local(
                chunk,
                delete_files=body.delete_files,
                delete_all_copies=body.delete_all_copies,
            )
            results.extend(res)
    deps.record_delete_log(results, body.delete_files)

    deleted = sum(1 for r in results if r.get("db_removed") or r.get("trashed"))
    trashed = sum(1 for r in results if r.get("trashed"))
    failed_deletions = [p for r in results for p in r.get("failed_paths", [])]
    return {
        "deleted": deleted,
        "trashed": trashed,
        "matched": len(matching_ids),
        "failed_deletions": failed_deletions,
        "results": results,
    }
