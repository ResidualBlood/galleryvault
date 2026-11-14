"""Browse listing use-case: filter normalization and response assembly.

Extracted from ``app/routers/galleries/listing.py`` (T9.2c).  The router keeps
FastAPI parameter validation and injects the repository factory plus the
serialisers through :class:`~.deps.LibraryDeps`, so the existing
``monkeypatch.setattr(galleries, ...)`` patch points stay effective.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ...app.params import (
    _dedupe_tags,
    _parse_posted,
    _parse_tag_filter,
    _resolve_search_tokens,
    _tags_for_galleries,
)
from ...scanners.base import CATEGORIES
from ..tag_translation import translated_tag
from .deps import LibraryDeps

__all__ = ["list_galleries_page"]


async def list_galleries_page(
    deps: LibraryDeps,
    session: Any,
    *,
    page: int,
    page_size: int,
    q: str | None,
    tags: str | None,
    exclude_tags: str | None,
    tag_mode: str,
    tag_match: str,
    category: str | None,
    order_by: str,
    read_status: str | None,
    min_rating: float | None,
    page_min: int | None,
    page_max: int | None,
    size_min: int | None,
    size_max: int | None,
    posted_from: str | None,
    posted_to: str | None,
    uploader: str | None,
    image_quality: str | None,
    storage_tier: str | None,
    min_local_rating: int | None,
    list_id: int | None,
    tags_limit: int | None,
) -> dict[str, object]:
    """Normalize the browse filters, page the repository and build the payload."""
    if category == "":
        category = None
    exclude_favorited = False
    if category == "__not_fav__":
        exclude_favorited = True
        category = None
    elif category and category not in CATEGORIES:
        raise HTTPException(
            status_code=422, detail=f"category must be one of {', '.join(CATEGORIES)}"
        )

    posted_from_dt = _parse_posted(posted_from)
    posted_to_dt = _parse_posted(posted_to, upper=True)

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

    repo = deps.repo_factory(session)
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
    tag_map = await _tags_for_galleries(deps.repo_factory(session), g_ids, tags_limit)
    progress_map = await deps.repo_factory(session).progress_for_galleries(g_ids)

    tag_str_parts = []
    if parsed_inc_tags:
        tag_str_parts.extend(
            f"{namespace}:{name}" if namespace else name for namespace, name in parsed_inc_tags
        )
    if parsed_exc_tags:
        tag_str_parts.extend(
            f"-{namespace}:{name}" if namespace else f"-{name}"
            for namespace, name in parsed_exc_tags
        )

    if deps.serialize_summary is None or deps.attr is None:
        raise RuntimeError("listing deps are missing serializers")
    attr = deps.attr
    serialize = deps.serialize_summary

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
            serialize(
                row,
                tag_map,
                reading_progress=progress_map.get(row.id, attr(row, "reading_progress", None)),
            )
            for row in rows
        ],
    }
