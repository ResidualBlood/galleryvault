"""Shared query-parameter parsing helpers for list/filter endpoints.

These helpers were previously private to ``app.routers.galleries`` and were
imported from there by ``app.routers.favorites``.  They are pure (or take a
repository argument), so they live here to keep router modules from reaching
into each other's private names.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import HTTPException

from ..metadata.sidecar import parse_datetime_utc

_IMAGE_QUALITY = frozenset({"original", "resample"})


_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_posted(value: str | None, upper: bool = False) -> datetime | None:
    """Parse a posted-at bound.

    Date-only values keep midnight for ``posted_from``; for ``posted_to``
    (``upper=True``) they advance to the next midnight so callers can use a
    strict ``<`` comparison and still include the whole end day. Explicit
    timestamps are always kept as-is.
    """
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    dt = parse_datetime_utc(raw)
    if dt is None:
        raise HTTPException(status_code=422, detail="invalid posted date")
    if upper and _DATE_ONLY_RE.match(raw):
        dt += timedelta(days=1)
    return dt


async def _tags_for_galleries(
    repo: object, gallery_ids: list[int], tags_limit: int | None
) -> dict[int, list[tuple[str, str]]]:
    """Fetch tag previews, passing a custom cap only when the client asked.

    Keeping the one-argument call for the default keeps existing repository
    doubles (which implement the historical signature) working.
    """
    limit = tags_limit if isinstance(tags_limit, int) else None
    if limit is None:
        return await repo.tags_for_galleries(gallery_ids)
    return await repo.tags_for_galleries(gallery_ids, limit)


def _tag_count(tag_map: dict[int, list[tuple[str, str]]], gallery_id: int) -> int:
    counts = getattr(tag_map, "counts", None) or {}
    if gallery_id in counts:
        return int(counts[gallery_id])
    return len(tag_map.get(gallery_id, []))


def _dedupe_tags(tags: list[tuple[str | None, str]]) -> list[tuple[str | None, str]]:
    seen: set[tuple[str | None, str]] = set()
    out: list[tuple[str | None, str]] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _parse_tag_filter(
    tags: str | None,
) -> tuple[list[tuple[str | None, str]], list[tuple[str | None, str]]]:
    include_tags: list[tuple[str | None, str]] = []
    exclude_tags: list[tuple[str | None, str]] = []
    for value in (tags or "").split(","):
        value = value.strip()
        if not value:
            continue
        is_exclude = False
        if value.startswith("-") and len(value) > 1:
            is_exclude = True
            value = value[1:].strip()
        if ":" in value:
            namespace, name = value.split(":", 1)
            namespace = namespace.strip() or None
        else:
            namespace, name = None, value
        if not name.strip() or len(name) > 200 or (namespace and len(namespace) > 32):
            raise HTTPException(status_code=422, detail="invalid tag")
        tag_tuple = (namespace, name.strip())
        if is_exclude:
            exclude_tags.append(tag_tuple)
        else:
            include_tags.append(tag_tuple)
    return include_tags, exclude_tags


async def _resolve_search_tokens(
    q: str,
) -> tuple[list[tuple[str | None, str]], list[tuple[str | None, str]], str, bool]:
    tokens = q.split()
    if not tokens:
        return [], [], "", False
    explicit_inc: list[tuple[str | None, str]] = []
    explicit_exc: list[tuple[str | None, str]] = []
    keywords: list[str] = []
    for token in tokens:
        # "-ns:name" or "-name" is an exclude tag, not a keyword
        if token.startswith("-") and len(token) > 1 and not token.startswith("--"):
            inner = token[1:]
            if ":" in inner:
                namespace, name = inner.split(":", 1)
                namespace = namespace.strip() or None
                name = name.strip()
                if name:
                    explicit_exc.append((namespace, name))
                    continue
            else:
                name = inner.strip()
                if name:
                    explicit_exc.append((None, name))
                    continue
        if ":" in token:
            namespace, name = token.split(":", 1)
            namespace = namespace.strip() or None
            name = name.strip()
            if name:
                explicit_inc.append((namespace, name))
            else:
                keywords.append(token)
        else:
            keywords.append(token)
    return explicit_inc, explicit_exc, " ".join(keywords), bool(explicit_inc or explicit_exc)
