"""Favorites duplicates scan: group favorites and persist the result."""

from __future__ import annotations

import logging
from datetime import datetime

from ...app.state import app_state
from ...db.repositories.duplicates import DuplicateGroupRepository
from ...db.repository import FavoritesRepository
from ...db.session import safe_transaction
from ...logging import log_extra
from ...metadata.sidecar import normalize_posted, normalize_tags
from ..duplicates import find_duplicate_groups
from ..eh_metadata import refresh_gdata
from ..favorites import (
    _get_background_session_factory,
    favorites_metadata,
    remote_cover_data_batch,
)
from ..tag_translation import translated_tag

# Same logger name as the legacy module (CR1).
logger = logging.getLogger("galleryvault.services.favorites_worker")


async def run_duplicates_scan() -> None:
    session_factory = _get_background_session_factory()
    if not session_factory:
        return
    from ...app.dependencies import get_task_manager, resolve_display_title

    tm = get_task_manager()
    async with tm.track_task("duplicates") as tracker:
        tracker.update(stage="reading", done=0, total=0, last_error=None, groups=[])
        try:
            async with session_factory() as session:
                repo = FavoritesRepository(session)
                items = await repo.all_items()
                gids = list({item[1] for item in items})
                tracker.update(total=len(items), stage="analyzing")
                gallery_titles = await repo.gallery_titles_by_gid(gids)
                local_ids_all = [item[5] for item in items if item[5] is not None]
                tag_map = await repo.tags_for_gallery_ids(local_ids_all)

            tracker.update(done=len(items), stage="grouping")
            groups = find_duplicate_groups(items, gallery_titles=gallery_titles, tag_map=tag_map)
            group_items = [it for g in groups for it in g["items"]]
            cloud_pairs = [
                (it["gid"], it["token"]) for it in group_items if it["gallery_id"] is None
            ]
            tracker.update(stage="enriching")
            gmeta = await favorites_metadata(cloud_pairs) if cloud_pairs else {}
            for it in group_items:
                if it["gallery_id"] is not None:
                    en_title, jp_title = gallery_titles.get(it["gid"], (None, None))
                    it["title_jpn"] = jp_title
                    it["display_title"] = (
                        resolve_display_title(en_title or it.get("title"), jp_title)
                        or it.get("title")
                        or f"gid {it['gid']}"
                    )
                    if isinstance(it.get("posted_at"), datetime):
                        it["posted_at"] = it["posted_at"].isoformat()
                    it["tags"] = [
                        {"namespace": ns, "name": name, "display": translated_tag(ns, name)[1]}
                        for ns, name in tag_map.get(it["gallery_id"], [])
                    ]
                else:
                    meta = gmeta.get(it["gid"], {})
                    it["file_size"] = it["file_size"] or meta.get("file_size")
                    it["title_jpn"] = meta.get("title_jpn")
                    it["display_title"] = (
                        resolve_display_title(it["title"] or meta.get("title"), meta.get("title_jpn"))
                        or it["title"]
                        or f"gid {it['gid']}"
                    )
                    if "posted_at" in meta:
                        val = meta["posted_at"]
                        it["posted_at"] = val.isoformat() if isinstance(val, datetime) else val
                    else:
                        it["posted_at"] = normalize_posted(meta.get("posted"))
                    it["tags"] = [
                        {
                            "namespace": t["namespace"],
                            "name": t["name"],
                            "display": translated_tag(t["namespace"], t["name"])[1],
                        }
                        for t in normalize_tags(meta.get("tags", []))
                    ]
            cover_map = await remote_cover_data_batch(cloud_pairs, gmeta)
            for it in group_items:
                if it["gallery_id"] is None:
                    it["cover_data"] = cover_map.get(it["gid"])
            missing_posted = [
                (it["gid"], it["token"])
                for it in group_items
                if not it["posted_at"] and it["token"]
            ]
            if missing_posted and app_state.eh_client is not None:
                try:
                    if session_factory:
                        # No explicit transaction: refresh_gdata releases the
                        # connection before this gdata call and writes after.
                        async with session_factory() as session:
                            posted_meta = await refresh_gdata(
                                session, missing_posted, client=app_state.eh_client
                            )
                    else:
                        posted_meta = await app_state.eh_client.fetch_gmetadata(missing_posted)
                except Exception as exc:  # noqa: BLE001
                    posted_meta = {}
                    logger.warning(
                        "duplicate posted enrichment failed",
                        extra=log_extra(error=type(exc).__name__),
                    )
                local_write: dict[int, datetime] = {}
                for it in group_items:
                    if it["posted_at"] or it["gid"] not in posted_meta:
                        continue
                    posted = normalize_posted(posted_meta[it["gid"]].get("posted"))
                    if not posted:
                        continue
                    it["posted_at"] = posted
                    if it["gallery_id"] is not None:
                        local_write[it["gid"]] = datetime.fromisoformat(posted)
                if local_write:
                    async with session_factory() as session, session.begin():
                        await FavoritesRepository(session).update_posted_at(local_write)

            for g in groups:
                g.pop("legacy_keys", None)
            groups.sort(key=lambda g: -len(g["items"]))

            # Single write path (T5.2/T5.3): persist every group into
            # ``duplicate_groups`` (``kind='favorites'``).  Ignored groups are not
            # filtered out here: their dismissal lives on this kind's row, so
            # ``sync`` keeps it and a rescan cannot resurrect them.  The page
            # reads the open rows and ``tm.duplicates_state`` keeps progress
            # only, so a restart cannot lose the scan result.
            async with session_factory() as session, safe_transaction(session):
                await DuplicateGroupRepository(session).sync("favorites", groups)

            tracker.update(
                done=len(items),
                stage="done",
            )
        except Exception as exc:  # noqa: BLE001
            tracker.update(last_error=f"{type(exc).__name__}: {exc}", stage="error")
