"""Resolve titles and follow ExHentai replacement chains before enqueue."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from sqlalchemy import select

from ..app.state import app_state
from ..db.models import Gallery
from ..db.repository import GalleryRepository
from ..logging import log_extra
from .eh_client import EhClientError, GalleryGoneError
from .messages import GONE_DETAIL

logger = logging.getLogger(__name__)

MAX_FOLLOW_HOPS = 5


@dataclass
class PreparedGallery:
    gid: int
    token: str
    title: str | None = None
    title_jpn: str | None = None
    old_gid: int | None = None
    gone: bool = False
    already_local: bool = False


def _titles_of(info: dict | None) -> tuple[str | None, str | None]:
    if not info:
        return None, None
    title = (info.get("title") or None) or None
    title_jpn = (info.get("title_jpn") or None) or None
    if isinstance(title, str):
        title = title.strip() or None
    if isinstance(title_jpn, str):
        title_jpn = title_jpn.strip() or None
    return title, title_jpn


async def _cached_map(gids: list[int]) -> dict[int, dict]:
    session_cm = app_state.session_factory
    if session_cm is None or not gids:
        return {}
    cached: dict[int, dict] = {}
    async with session_cm() as session:
        cached = await GalleryRepository(session).metadata_map(gids)
        missing = [g for g in gids if g not in cached]
        if missing:
            rows = (
                await session.scalars(select(Gallery).where(Gallery.gid.in_(missing)))
            ).all()
            for row in rows:
                cached[int(row.gid)] = {
                    "title": row.title,
                    "title_jpn": getattr(row, "title_jpn", None),
                    "token": row.token,
                    "expunged": bool(getattr(row, "expunged", False)),
                }
    return cached


async def _local_gids(gids: list[int]) -> set[int]:
    session_cm = app_state.session_factory
    if session_cm is None or not gids:
        return set()
    async with session_cm() as session:
        stmt = select(Gallery.gid).where(
            Gallery.gid.in_(list(dict.fromkeys(gids))),
            Gallery.expunged.is_(False),
        )
        if hasattr(Gallery, "trashed"):
            stmt = stmt.where(Gallery.trashed.is_(False))
        rows = (await session.scalars(stmt)).all()
    return {int(gid) for gid in rows}


async def _html_resolve(
    client: object, gid: int, token: str
) -> PreparedGallery | None:
    fetch_meta = getattr(client, "fetch_gallery_metadata", None)
    if fetch_meta is None:
        return None
    try:
        data = await fetch_meta(gid, token)
    except GalleryGoneError:
        return PreparedGallery(gid=gid, token=token, gone=True)
    except EhClientError as exc:
        logger.info(
            "download prepare html fetch failed",
            extra=log_extra(gid=gid, error=type(exc).__name__),
        )
        return None
    replaced = getattr(data, "replaced_by", None)
    title = getattr(data, "title", None) or None
    title_jpn = getattr(data, "title_jpn", None)
    new_token = getattr(data, "token", None) or token
    if replaced:
        new_gid, new_tok = replaced
        return PreparedGallery(
            gid=int(new_gid),
            token=str(new_tok),
            title=title,
            title_jpn=title_jpn,
            old_gid=gid,
        )
    if not title and not title_jpn:
        return PreparedGallery(gid=gid, token=token, gone=True)
    return PreparedGallery(
        gid=gid, token=new_token, title=title, title_jpn=title_jpn
    )


async def _resolve_one(
    client: object | None,
    gid: int,
    token: str,
    *,
    cache: dict[int, dict],
    gdata: dict[int, dict],
    hops: int,
    html_cache: dict[int, PreparedGallery | None] | None = None,
    html_tokens: dict[int, str] | None = None,
) -> PreparedGallery:
    if html_cache is None:
        html_cache = {}
    if hops >= MAX_FOLLOW_HOPS:
        title, title_jpn = _titles_of(gdata.get(gid) or cache.get(gid))
        return PreparedGallery(gid=gid, token=token, title=title, title_jpn=title_jpn)

    title, title_jpn = _titles_of(gdata.get(gid) or cache.get(gid))
    if client is None:
        return PreparedGallery(gid=gid, token=token, title=title, title_jpn=title_jpn)
    if gid not in html_cache:
        if html_tokens is not None:
            html_tokens[gid] = token
        html_cache[gid] = await _html_resolve(client, gid, token)
    raw = html_cache[gid]
    if raw is None:
        return PreparedGallery(gid=gid, token=token, title=title, title_jpn=title_jpn)
    html = replace(raw)
    if html.gone:
        html.title = html.title or title
        html.title_jpn = html.title_jpn or title_jpn
        return html
    if html.old_gid or html.gid != gid:
        nested = await _resolve_one(
            client,
            html.gid,
            html.token,
            cache=cache,
            gdata=gdata,
            hops=hops + 1,
            html_cache=html_cache,
            html_tokens=html_tokens,
        )
        nested.old_gid = nested.old_gid or gid
        if not nested.title and not nested.title_jpn:
            nested.title = html.title or title
            nested.title_jpn = html.title_jpn or title_jpn
        return nested
    html.title = html.title or title
    html.title_jpn = html.title_jpn or title_jpn
    return html


async def prepare_galleries(pairs: list[tuple[int, str]]) -> list[PreparedGallery]:
    """Resolve titles and follow replacement chains. Never raises on EH errors."""
    if not pairs:
        return []
    gids = [int(gid) for gid, _ in pairs]
    cache = await _cached_map(gids)
    client = app_state.eh_client
    gdata: dict[int, dict] = {}
    html_cache: dict[int, PreparedGallery | None] = {}
    html_tokens: dict[int, str] = {}

    async def _resolve_all() -> list[PreparedGallery]:
        out: list[PreparedGallery] = []
        for gid, token in pairs:
            out.append(
                await _resolve_one(
                    client,
                    int(gid),
                    token,
                    cache=cache,
                    gdata=gdata,
                    hops=0,
                    html_cache=html_cache,
                    html_tokens=html_tokens,
                )
            )
        return out

    results = await _resolve_all()
    if client is not None:
        need: list[tuple[int, str]] = []
        seen: set[int] = set()
        for gid, raw in html_cache.items():
            if raw is None and gid not in seen:
                tok = html_tokens.get(gid)
                if tok:
                    need.append((gid, tok))
                    seen.add(gid)
        if need:
            try:
                fetched = await client.fetch_gmetadata(need)
            except EhClientError as exc:
                logger.info(
                    "download prepare gdata failed",
                    extra=log_extra(error=type(exc).__name__),
                )
                fetched = {}
            gdata.update(fetched or {})
            results = await _resolve_all()
    follow_gids = [p.gid for p in results if p.old_gid and not p.gone]
    local = await _local_gids(follow_gids)
    for prepared in results:
        if prepared.old_gid and prepared.gid in local:
            prepared.already_local = True
    return results


def gone_message() -> str:
    return GONE_DETAIL
