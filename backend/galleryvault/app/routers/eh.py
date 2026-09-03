"""ExHentai discovery / search endpoints."""

from __future__ import annotations

import re
import time
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ...db.models import FavoriteItem, Gallery
from ...services.eh_client import EhClient, EhClientError, EhSearchResult, SearchGallery
from ..dependencies import db_error, get_current_settings, get_session
from ..state import app_state

router = APIRouter()

_EH_CAT_BITS: dict[str, int] = {
    "doujinshi": 1,
    "manga": 2,
    "artistcg": 4,
    "gamecg": 8,
    "western": 16,
    "non-h": 32,
    "image_set": 64,
    "cosplay": 128,
    "asianporn": 256,
    "misc": 512,
}
_EH_CAT_ALL = 1023
_NEXT_CURSOR_RE = re.compile(r"^\d+-\d+$")
_TOPLIST_CURSOR_RE = re.compile(r"^\d+$")
_SEARCH_TTL_OK = 90.0
_SEARCH_TTL_ERR = 15.0
_SEARCH_CACHE_MAX = 64


def parse_category_param(category: str | None) -> int | None:
    """Map ``category`` query to ExHentai ``f_cats`` (disabled-bit mask).

    An integer 0–1023 is passed through as the site bitmask. Comma-separated
    names are treated as *enabled* categories and inverted.
    """
    if category is None:
        return None
    raw = str(category).strip()
    if not raw:
        return None
    if raw.isdigit():
        value = int(raw)
        if 0 <= value <= _EH_CAT_ALL:
            return value
        raise HTTPException(status_code=422, detail="category out of range")
    enabled = 0
    for part in raw.split(","):
        name = part.strip().casefold().replace(" ", "_")
        if name in {"imageset", "image-set"}:
            name = "image_set"
        if name in {"asian_porn", "asian-porn"}:
            name = "asianporn"
        if name == "nonh":
            name = "non-h"
        bit = _EH_CAT_BITS.get(name)
        if bit is None:
            raise HTTPException(status_code=422, detail="unknown category")
        enabled |= bit
    if enabled in (0, _EH_CAT_ALL):
        return 0
    return _EH_CAT_ALL ^ enabled


def _search_cache_key(
    q: str,
    f_cats: int | None,
    min_rating: float | None,
    next_cursor: str | None,
    list_type: str = "search",
    tl: int | None = None,
) -> tuple[str, str, str, str, str, str]:
    rating = "" if min_rating is None else str(min_rating)
    cats = "" if f_cats is None else str(f_cats)
    tl_key = "" if list_type != "toplist" or tl is None else str(tl)
    return (q or "", cats, rating, next_cursor or "", list_type or "search", tl_key)


def _search_cache_get(key: tuple[str, ...]) -> dict[str, Any] | None:
    cache = app_state.extra.get("eh_search_cache")
    if not isinstance(cache, dict):
        return None
    hit = cache.get(key)
    if not hit:
        return None
    expires, payload = hit
    if float(expires) < time.monotonic():
        cache.pop(key, None)
        return None
    return payload


def _search_cache_set(key: tuple[str, ...], payload: dict[str, Any], ttl: float) -> None:
    cache = app_state.extra.get("eh_search_cache")
    if not isinstance(cache, dict):
        cache = {}
        app_state.extra["eh_search_cache"] = cache
    now = time.monotonic()
    if len(cache) >= _SEARCH_CACHE_MAX:
        expired = [k for k, (exp, _) in cache.items() if float(exp) < now]
        for old in expired:
            cache.pop(old, None)
        while len(cache) >= _SEARCH_CACHE_MAX:
            oldest = min(cache, key=lambda k: cache[k][0])
            cache.pop(oldest, None)
    cache[key] = (now + ttl, payload)


def _gallery_payload(item: SearchGallery) -> dict[str, Any]:
    return {
        "gid": item.gid,
        "token": item.token,
        "title": item.title,
        "url": item.url,
        "thumb": item.thumb,
        "category": item.category,
        "pages": item.pages,
        "rating": item.rating,
    }


async def attach_search_badges(
    session: Any, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """JOIN local ``galleries.gid`` / ``favorite_items.gid`` onto search rows."""
    gids = [int(it["gid"]) for it in items if it.get("gid") is not None]
    if not gids:
        return items
    gal_rows = (
        await session.execute(
            select(Gallery.gid, Gallery.id).where(
                Gallery.gid.in_(gids),
                Gallery.trashed.is_(False),
            )
        )
    ).all()
    library: dict[int, int] = {}
    for gid, gallery_id in gal_rows:
        if gid is None:
            continue
        library[int(gid)] = int(gallery_id)
    fav_rows = (
        await session.execute(
            select(FavoriteItem.gid, FavoriteItem.favcat).where(FavoriteItem.gid.in_(gids))
        )
    ).all()
    favs: dict[int, int] = {}
    for gid, favcat in fav_rows:
        if gid is None:
            continue
        gid_i = int(gid)
        if gid_i not in favs:
            favs[gid_i] = int(favcat)
    for it in items:
        gid = int(it["gid"])
        gallery_id = library.get(gid)
        it["in_library"] = gallery_id is not None
        it["gallery_id"] = gallery_id
        it["favorited"] = gid in favs
        it["favcat"] = favs.get(gid)
        it["downloaded"] = gallery_id is not None
    return items


def _result_items(result: EhSearchResult) -> list[dict[str, Any]]:
    return [_gallery_payload(item) for item in result.items]


_EH_LISTS = frozenset({"search", "popular", "watched", "toplist"})
_EH_TOPLIST_TL = frozenset({11, 12, 13, 15})


@router.get("/api/eh/search")
async def eh_search(
    q: str = "",
    category: str | None = None,
    min_rating: float | None = Query(default=None, ge=0, le=5),
    next_cursor: str | None = Query(default=None, alias="next"),
    list_type: Annotated[str, Query(alias="list")] = "search",
    tl: int | None = None,
) -> dict[str, Any]:
    kind = (list_type or "search").strip().lower()
    if kind not in _EH_LISTS:
        raise HTTPException(status_code=422, detail="invalid list")
    if kind == "toplist":
        tl = 15 if tl is None else int(tl)
        if tl not in _EH_TOPLIST_TL:
            raise HTTPException(status_code=422, detail="invalid toplist tl")
    else:
        tl = None
    if next_cursor:
        next_cursor = str(next_cursor).strip()
        if kind == "toplist":
            if not _TOPLIST_CURSOR_RE.fullmatch(next_cursor) or not (
                0 <= int(next_cursor) < 200
            ):
                raise HTTPException(status_code=422, detail="invalid next cursor")
        else:
            if not _NEXT_CURSOR_RE.fullmatch(next_cursor):
                raise HTTPException(status_code=422, detail="invalid next cursor")
    else:
        next_cursor = None
    f_cats = parse_category_param(category)
    key = _search_cache_key(
        q.strip() if q else "", f_cats, min_rating, next_cursor, kind, tl
    )
    payload = _search_cache_get(key)
    if payload is None:
        client = app_state.eh_client
        settings = get_current_settings()
        try:
            if client is not None:
                result = await client.search_galleries(
                    q=q,
                    f_cats=f_cats,
                    min_rating=min_rating,
                    next_cursor=next_cursor,
                    list_type=kind,
                    tl=tl,
                )
            else:
                async with EhClient(
                    settings, max_concurrency=settings.exhentai_max_concurrency
                ) as tmp:
                    result = await tmp.search_galleries(
                        q=q,
                        f_cats=f_cats,
                        min_rating=min_rating,
                        next_cursor=next_cursor,
                        list_type=kind,
                        tl=tl,
                    )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except EhClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        payload = {
            "state": result.state,
            "items": _result_items(result),
            "next": result.next_cursor,
        }
        ttl = _SEARCH_TTL_OK if result.state in {"ok", "empty"} else _SEARCH_TTL_ERR
        _search_cache_set(key, payload, ttl)

    items = [dict(it) for it in payload.get("items") or []]
    state = str(payload.get("state") or "ok")
    if items and state == "ok":
        try:
            async for session in get_session():
                items = await attach_search_badges(session, items)
                break
        except SQLAlchemyError as exc:
            raise db_error(exc) from exc
    else:
        for it in items:
            it.setdefault("in_library", False)
            it.setdefault("gallery_id", None)
            it.setdefault("favorited", False)
            it.setdefault("favcat", None)
            it.setdefault("downloaded", False)
    return {
        "state": state,
        "items": items,
        "next": payload.get("next"),
        "q": q or "",
        "category": category,
        "min_rating": min_rating,
        "list": kind,
        "tl": tl,
    }
