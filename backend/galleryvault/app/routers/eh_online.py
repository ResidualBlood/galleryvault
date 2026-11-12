"""Online gallery detail, lazy preview pages and direct image-URL resolution.

This module exposes gallery metadata, the per-preview-page index plus H@H
sprite thumbnails, a local-library badge lookup that never talks to ExHentai,
and the single-page resolve endpoint the online reader uses to fetch images
straight from H@H.  Resolve is one ``showpage`` per page (never bytes and never
the image semaphore); see :mod:`galleryvault.services.online_resolve`.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from ...db.models import DownloadTask, FavoriteItem, Gallery
from ...services.eh_client import (
    EhAuthRequiredError,
    EhBannedError,
    EhChallengeError,
    EhClientError,
    OnlineGalleryDetail,
    PreviewPage,
)
from ...services.online_resolve import OnlineResolveError, resolve_online_page
from ..core.eh_client_manager import EhClientManager
from ..dependencies import (
    db_error,
    get_eh_client_manager,
    get_session,
    resolve_session,
)
from ..exceptions import EhClientUnavailableError
from ..state import app_state

logger = logging.getLogger(__name__)

router = APIRouter()

_DETAIL_CACHE = "eh_online_detail_cache"
_PAGES_CACHE = "eh_online_pages_cache"
_PAGES_META_CACHE = "eh_online_pages_meta"
_CACHE_MAX = 64
_TTL_OK = 90.0
_TTL_ERR = 15.0
_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{1,64}$")
_MAX_STATUS_GIDS = 100
_DOWNLOAD_STATUSES = ("pending", "downloading", "failed")


def _cache_get(bucket: str, key: tuple[Any, ...]) -> dict[str, Any] | None:
    cache = app_state.extra.get(bucket)
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


def _cache_set(
    bucket: str, key: tuple[Any, ...], payload: dict[str, Any], ttl: float
) -> None:
    cache = app_state.extra.get(bucket)
    if not isinstance(cache, dict):
        cache = {}
        app_state.extra[bucket] = cache
    now = time.monotonic()
    if len(cache) >= _CACHE_MAX:
        expired = [k for k, (exp, _) in cache.items() if float(exp) < now]
        for old in expired:
            cache.pop(old, None)
        while len(cache) >= _CACHE_MAX:
            oldest = min(cache, key=lambda k: cache[k][0])
            cache.pop(oldest, None)
    cache[key] = (now + ttl, payload)


def _validate_gid(gid: int) -> int:
    if int(gid) <= 0:
        raise HTTPException(status_code=422, detail="invalid gid")
    return int(gid)


def _validate_token(token: str) -> str:
    # Tokens are hex on ExHentai; anything else would be interpolated into an
    # upstream path, so reject it before touching the client.
    if not _TOKEN_RE.fullmatch(token or ""):
        raise HTTPException(status_code=422, detail="invalid token")
    return str(token)


def _resolve_client_manager(manager: Any) -> EhClientManager:
    if isinstance(manager, EhClientManager):
        return manager
    return get_eh_client_manager()


def _state_for_error(exc: Exception) -> str:
    if isinstance(exc, EhChallengeError):
        return "challenge"
    if isinstance(exc, EhBannedError):
        return "banned"
    if isinstance(exc, EhAuthRequiredError):
        return "auth"
    return "error"


def _thumb_payload(thumb: Any) -> dict[str, Any] | None:
    if thumb is None:
        return None
    return {
        "url": thumb.url,
        "x": int(thumb.x),
        "y": int(thumb.y),
        "w": int(thumb.w),
        "h": int(thumb.h),
    }


def _detail_payload(detail: OnlineGalleryDetail) -> dict[str, Any]:
    newer = detail.newer
    return {
        "gid": int(detail.gid),
        "token": detail.token,
        "title": detail.title,
        "title_jpn": detail.title_jpn,
        "category": detail.category,
        "uploader": detail.uploader,
        "posted": detail.posted,
        "pages": detail.pages,
        "rating": detail.rating,
        "file_size": detail.file_size,
        "thumb": detail.thumb,
        "tags": [dict(tag) for tag in detail.tags],
        "newer": {"gid": int(newer[0]), "token": newer[1]} if newer else None,
        "parent_gid": detail.parent_gid,
    }


async def latest_downloads(session: Any, gids: list[int]) -> dict[int, dict[str, Any]]:
    """Newest ``pending`` / ``downloading`` / ``failed`` task per gid.

    A finished import is already visible through ``in_library``; only the
    actionable states matter for the badge, so ``success``/``cancelled`` rows
    are excluded.
    """
    if not gids:
        return {}
    latest = (
        select(DownloadTask.gid.label("gid"), func.max(DownloadTask.id).label("max_id"))
        .where(
            DownloadTask.gid.in_(gids),
            DownloadTask.status.in_(_DOWNLOAD_STATUSES),
        )
        .group_by(DownloadTask.gid)
        .subquery()
    )
    rows = (
        await session.execute(
            select(
                DownloadTask.id,
                DownloadTask.gid,
                DownloadTask.status,
                DownloadTask.current_page,
                DownloadTask.total_pages,
            ).join(latest, DownloadTask.id == latest.c.max_id)
        )
    ).all()
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        try:
            task_id, gid, status = int(row[0]), int(row[1]), row[2]
        except (TypeError, ValueError, IndexError):
            continue
        if not isinstance(status, str):
            # Guard against test doubles / drifted row shapes instead of
            # leaking a bogus badge into the response.
            continue
        total_pages = row[4] if len(row) > 4 else None
        result[gid] = {
            "id": task_id,
            "status": status,
            "current_page": int(row[3] or 0) if len(row) > 3 else 0,
            "total_pages": int(total_pages) if total_pages is not None else None,
        }
    return result


async def local_gallery_status(
    session: Any, gids: list[int]
) -> dict[int, dict[str, Any]]:
    """Local-only badges for ``gids`` (no ExHentai traffic)."""
    result: dict[int, dict[str, Any]] = {
        int(gid): {
            "in_library": False,
            "gallery_id": None,
            "favorited": False,
            "favcat": None,
            "download": None,
        }
        for gid in gids
    }
    if not gids:
        return result
    gal_rows = (
        await session.execute(
            select(Gallery.gid, Gallery.id).where(
                Gallery.gid.in_(gids),
                Gallery.trashed.is_(False),
            )
        )
    ).all()
    for row in gal_rows:
        try:
            gid = int(row[0])
        except (TypeError, ValueError):
            continue
        info = result.setdefault(
            gid,
            {
                "in_library": False,
                "gallery_id": None,
                "favorited": False,
                "favcat": None,
                "download": None,
            },
        )
        info["in_library"] = True
        info["gallery_id"] = int(row[1])
    fav_rows = (
        await session.execute(
            select(FavoriteItem.gid, FavoriteItem.favcat).where(FavoriteItem.gid.in_(gids))
        )
    ).all()
    for row in fav_rows:
        try:
            gid = int(row[0])
            favcat = int(row[1])
        except (TypeError, ValueError):
            continue
        info = result.get(gid)
        if info is None:
            continue
        if not info["favorited"]:
            info["favcat"] = favcat
        info["favorited"] = True
    downloads = await latest_downloads(session, gids)
    for gid, download in downloads.items():
        info = result.get(gid)
        if info is not None:
            info["download"] = download
    return result


async def _fetch_detail(
    client_mgr: Any, gid: int, token: str
) -> dict[str, Any]:
    key = ("detail", gid, token)
    cached = _cache_get(_DETAIL_CACHE, key)
    if cached is not None:
        return cached
    mgr = _resolve_client_manager(client_mgr)
    try:
        async with mgr.client_context() as client:
            detail = await client.fetch_online_gallery(gid, token)
    except (EhChallengeError, EhBannedError, EhAuthRequiredError) as exc:
        payload: dict[str, Any] = {"state": _state_for_error(exc), "gallery": None}
        _cache_set(_DETAIL_CACHE, key, payload, _TTL_ERR)
        return payload
    except (EhClientError, EhClientUnavailableError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    payload = {"state": "ok", "gallery": _detail_payload(detail)}
    _cache_set(_DETAIL_CACHE, key, payload, _TTL_OK)
    return payload


@router.get("/api/eh/galleries/{gid}/{token}")
async def eh_online_gallery_detail(
    gid: int,
    token: str,
    session: Any = Depends(get_session),  # noqa: B008
    client_mgr: Any = Depends(get_eh_client_manager),  # noqa: B008
) -> dict[str, Any]:
    gid = _validate_gid(gid)
    token = _validate_token(token)
    payload = await _fetch_detail(client_mgr, gid, token)
    gallery = payload.get("gallery")
    if gallery is not None:
        actual_session = await resolve_session(session)
        try:
            status = (await local_gallery_status(actual_session, [gid])).get(gid, {})
        except SQLAlchemyError as exc:
            raise db_error(exc) from exc
        gallery = dict(gallery)
        gallery.update(
            in_library=bool(status.get("in_library")),
            gallery_id=status.get("gallery_id"),
            favorited=bool(status.get("favorited")),
            favcat=status.get("favcat"),
            download=status.get("download"),
        )
    return {"state": str(payload.get("state") or "ok"), "gallery": gallery}


async def _fetch_preview_page(
    client_mgr: Any, gid: int, token: str, p: int
) -> dict[str, Any]:
    key = ("pages", gid, token, p)
    cached = _cache_get(_PAGES_CACHE, key)
    if cached is not None:
        return cached
    mgr = _resolve_client_manager(client_mgr)
    try:
        async with mgr.client_context() as client:
            preview: PreviewPage = await client.fetch_gallery_preview_page(gid, token, p)
    except (EhChallengeError, EhBannedError, EhAuthRequiredError) as exc:
        payload: dict[str, Any] = {
            "state": _state_for_error(exc),
            "total": None,
            "items": [],
            "ptokens": {},
            "per_page": 0,
        }
        _cache_set(_PAGES_CACHE, key, payload, _TTL_ERR)
        return payload
    except (EhClientError, EhClientUnavailableError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    payload = {
        "state": "ok",
        "total": preview.total,
        "items": preview.items,
        "ptokens": preview.ptokens,
        "per_page": len(preview.items) if p == 0 else 0,
    }
    _cache_set(_PAGES_CACHE, key, payload, _TTL_OK)
    if p == 0 and payload["per_page"]:
        _cache_set(
            _PAGES_META_CACHE,
            ("meta", gid, token),
            {"per_page": payload["per_page"]},
            _TTL_OK,
        )
    return payload


@router.get("/api/eh/galleries/{gid}/{token}/pages")
async def eh_online_pages(
    gid: int,
    token: str,
    p: int = Query(default=0, ge=0),
    client_mgr: Any = Depends(get_eh_client_manager),  # noqa: B008
) -> dict[str, Any]:
    gid = _validate_gid(gid)
    token = _validate_token(token)
    payload = await _fetch_preview_page(client_mgr, gid, token, p)
    items = [
        {"index": int(item.index), "thumb": _thumb_payload(item.thumb)}
        for item in payload.get("items") or []
    ]
    per_page = int(payload.get("per_page") or 0)
    if not per_page:
        meta = _cache_get(_PAGES_META_CACHE, ("meta", gid, token))
        per_page = int((meta or {}).get("per_page") or len(items))
    return {
        "state": str(payload.get("state") or "ok"),
        "p": p,
        "per_page": per_page,
        "total": payload.get("total"),
        "items": items,
    }


@router.get("/api/eh/galleries/{gid}/{token}/pages/{n}/resolve")
async def eh_online_resolve_page(
    gid: int,
    token: str,
    n: int,
    retry: int = Query(default=0, ge=0, le=2),
    client_mgr: Any = Depends(get_eh_client_manager),  # noqa: B008
) -> dict[str, Any]:
    """Resolve one page to a direct H@H image URL (browser fetches the bytes)."""
    gid = _validate_gid(gid)
    token = _validate_token(token)
    if n <= 0:
        raise HTTPException(status_code=404, detail={"code": "page_out_of_range"})
    try:
        return await resolve_online_page(client_mgr, gid, token, n, retry=retry)
    except OnlineResolveError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code}
        ) from exc


def _parse_status_gids(raw: str) -> list[int]:
    value = (raw or "").strip()
    if not value:
        return []
    parts = [part.strip() for part in value.split(",")]
    if len(parts) > _MAX_STATUS_GIDS:
        raise HTTPException(status_code=422, detail="too many gids (max 100)")
    gids: list[int] = []
    seen: set[int] = set()
    for part in parts:
        if not part.isdigit():
            raise HTTPException(status_code=422, detail="invalid gid")
        gid = int(part)
        if gid <= 0:
            raise HTTPException(status_code=422, detail="invalid gid")
        if gid not in seen:
            seen.add(gid)
            gids.append(gid)
    return gids


@router.get("/api/eh/status")
async def eh_local_status(
    gids: str = Query(default=""),
    session: Any = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    parsed = _parse_status_gids(gids)
    if not parsed:
        return {"items": []}
    actual_session = await resolve_session(session)
    try:
        status = await local_gallery_status(actual_session, parsed)
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    items = []
    for gid in parsed:
        info = status.get(gid, {})
        download = info.get("download") or {}
        items.append(
            {
                "gid": gid,
                "in_library": bool(info.get("in_library")),
                "gallery_id": info.get("gallery_id"),
                "favorited": bool(info.get("favorited")),
                "favcat": info.get("favcat"),
                "download_status": download.get("status"),
            }
        )
    return {"items": items}
