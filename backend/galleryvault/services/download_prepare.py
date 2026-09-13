"""Resolve titles and follow ExHentai replacement chains before enqueue."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select

from ..app.state import app_state
from ..db.models import Gallery
from ..db.repository import GalleryRepository
from ..logging import log_extra
from .eh_client import GalleryGoneError
from .eh_metadata import enrich_html_newer, refresh_gdata
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


async def prepare_galleries(pairs: list[tuple[int, str]]) -> list[PreparedGallery]:
    """Resolve titles and follow replacement chains. Never raises on EH errors."""
    if not pairs:
        return []
    gids = [int(gid) for gid, _ in pairs]
    cache = await _cached_map(gids)
    client = app_state.eh_client
    session_cm = app_state.session_factory

    # 1. Batch refresh missing or cold gdata into cache and persist to DB
    if session_cm is not None:
        try:
            async with session_cm() as session:
                refreshed = await refresh_gdata(session, pairs, client=client)
                cache.update(refreshed)
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "download prepare refresh_gdata failed",
                extra=log_extra(error=type(exc).__name__),
            )
    elif client is not None and hasattr(client, "fetch_gmetadata"):
        try:
            fetched = await client.fetch_gmetadata(pairs)
            cache.update(fetched)
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "download prepare gmetadata fallback failed",
                extra=log_extra(error=type(exc).__name__),
            )

    # 2. Resolve each gallery individually
    async def _resolve_one(
        gid: int,
        token: str,
        hops: int = 0,
        old_gid: int | None = None,
    ) -> PreparedGallery:
        meta = cache.get(gid) or {}
        title, title_jpn = _titles_of(meta)
        if hops >= MAX_FOLLOW_HOPS:
            return PreparedGallery(
                gid=gid, token=token, title=title, title_jpn=title_jpn, old_gid=old_gid
            )

        is_expunged = bool(meta.get("expunged", False))
        has_newer = meta.get("newer_gid") is not None
        is_replaced = bool(meta.get("is_replaced", False))

        # Normal, non-expunged gallery with no replacement flag:
        # use gdata title directly without requesting HTML /g/.
        if (
            not is_expunged
            and not has_newer
            and not is_replaced
            and (title or title_jpn or client is None)
        ):
            return PreparedGallery(
                gid=gid,
                token=token,
                title=title,
                title_jpn=title_jpn,
                old_gid=old_gid,
                gone=False,
            )

        # HTML probe only for expunged, known newer banner, or missing title
        newer_pair: tuple[int, str] | None = None
        html_gone = False
        html_title: str | None = None
        html_title_jpn: str | None = None

        if client is not None:
            if session_cm is not None:
                try:
                    async with session_cm() as session:
                        newer_pair = await enrich_html_newer(session, gid, token, client=client)
                except GalleryGoneError:
                    html_gone = True
                except Exception as exc:  # noqa: BLE001
                    logger.info(
                        "download prepare enrich_html_newer failed",
                        extra=log_extra(gid=gid, error=type(exc).__name__),
                    )
            else:
                fetch_meta = getattr(client, "fetch_gallery_metadata", None) or getattr(
                    client, "fetch_gallery", None
                )
                if fetch_meta is not None:
                    try:
                        data = await fetch_meta(gid, token)
                        replaced = getattr(data, "replaced_by", None)
                        if replaced:
                            newer_pair = (int(replaced[0]), str(replaced[1]))
                        html_title = getattr(data, "title", None) or None
                        html_title_jpn = getattr(data, "title_jpn", None) or None
                    except GalleryGoneError:
                        html_gone = True
                    except Exception as exc:  # noqa: BLE001
                        logger.info(
                            "download prepare html fetch failed",
                            extra=log_extra(gid=gid, error=type(exc).__name__),
                        )

        title = title or html_title
        title_jpn = title_jpn or html_title_jpn

        # If replaced by newer gallery: follow chain
        if newer_pair is not None:
            new_gid, new_token = newer_pair
            if new_gid not in cache:
                if session_cm is not None:
                    try:
                        async with session_cm() as session:
                            new_refreshed = await refresh_gdata(
                                session, [(new_gid, new_token)], client=client
                            )
                            cache.update(new_refreshed)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("download prepare chain refresh failed: %s", exc)
                elif client and hasattr(client, "fetch_gmetadata"):
                    try:
                        fetched = await client.fetch_gmetadata([(new_gid, new_token)])
                        cache.update(fetched)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("download prepare chain fetch failed: %s", exc)

            nested = await _resolve_one(
                new_gid,
                new_token,
                hops=hops + 1,
                old_gid=old_gid or gid,
            )
            nested.title = nested.title or title
            nested.title_jpn = nested.title_jpn or title_jpn
            return nested

        if is_expunged or html_gone or (not title and not title_jpn and client is not None):
            return PreparedGallery(
                gid=gid,
                token=token,
                title=title,
                title_jpn=title_jpn,
                old_gid=old_gid,
                gone=True,
            )

        return PreparedGallery(
            gid=gid,
            token=token,
            title=title,
            title_jpn=title_jpn,
            old_gid=old_gid,
            gone=False,
        )

    results: list[PreparedGallery] = []
    for gid, token in pairs:
        results.append(await _resolve_one(int(gid), token, hops=0))

    follow_gids = [p.gid for p in results if p.old_gid and not p.gone]
    local = await _local_gids(follow_gids)
    for prepared in results:
        if prepared.old_gid and prepared.gid in local:
            prepared.already_local = True
    return results


def gone_message() -> str:
    return GONE_DETAIL
