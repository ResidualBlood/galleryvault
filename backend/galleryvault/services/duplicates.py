from __future__ import annotations

import asyncio
from typing import Any

from gallery_dedup import (
    DUP_CORE_MIN_EFFECTIVE_LEN,
    DUP_SCORE_ARTIST_ONE_EMPTY,
    DUP_SCORE_ARTIST_SAME,
    DUP_SCORE_CORE_EXACT,
    DUP_SCORE_THRESHOLD,
    _CandidateItem,
    _cluster_duplicate_candidates,
    _core_effective_length,
    artist_from_title,
    calculate_duplicate_score,
    duplicate_group_is_ignored,
    extract_duplicate_artist_and_core,
    find_duplicate_groups,
    find_gallery_duplicate_groups,
    normalize_title,
)

# Process-wide guard shared by the HTTP refresh endpoint and the scan worker:
# both read the same in-memory snapshot, so overlapping scans only double the
# full-library read and the memory peak.  Callers go through
# ``scan_library_cross_gid_duplicates_locked`` instead of touching this lock.
cross_gid_scan_lock = asyncio.Lock()


async def scan_library_cross_gid_duplicates_locked(
    session_factory: Any = None, *, wait: bool
) -> list[dict[str, Any]] | None:
    """Run the cross-gid scan while holding ``cross_gid_scan_lock``.

    ``wait=False`` returns ``None`` when a scan already owns the lock so the
    HTTP endpoint can answer 409 instead of queueing; ``wait=True`` waits for
    the running scan and then runs its own (scan-worker tail, T11).
    """
    if not wait and cross_gid_scan_lock.locked():
        return None
    async with cross_gid_scan_lock:
        return await scan_library_cross_gid_duplicates(session_factory)


def _gallery_candidate(row: Any) -> dict[str, Any]:
    """Materialise a ``galleries`` row before it leaves the event loop.

    ``find_gallery_duplicate_groups`` runs in a worker thread; plain dicts keep
    ORM instances and their lazy-load state out of that thread.
    """
    return {
        "id": row.id,
        "gid": row.gid,
        "title": row.title,
        "title_jpn": row.title_jpn,
        "file_size": row.file_size,
        "pages": getattr(row, "pages", None),
        "page_count": row.page_count,
        "file_count": row.file_count,
        "category": row.category,
        "storage_path": row.storage_path,
        "storage_type": row.storage_type,
        "token": row.token,
    }


async def _artist_tag_map(fav_repo: Any, gallery_ids: list[int]) -> dict[int, list[tuple[str, str]]]:
    # Dedup only reads artist tags (gallery_dedup/__init__.py:513-516).  Prefer
    # the narrowed query; repositories/test doubles that only expose the
    # generic loader still work.
    load_tags = getattr(fav_repo, "artist_tags_for_gallery_ids", None)
    if load_tags is None:
        load_tags = fav_repo.tags_for_gallery_ids
    return await load_tags(gallery_ids)


async def scan_library_cross_gid_duplicates(
    session_factory: Any = None,
) -> list[dict[str, Any]]:
    """Scan library galleries and uningested favorites across gids and cache result in app_state."""
    if session_factory is None:
        from ..app.state import app_state

        if not app_state.session_factory:
            session_factory = None
        else:
            session_factory = app_state.background_session_factory or app_state.session_factory
    if not session_factory:
        return []

    from sqlalchemy import select
    from sqlalchemy.orm import load_only

    from ..db.models import FavoriteItem, Gallery
    from ..db.repository import FavoritesRepository

    async with session_factory() as session:
        # Only the columns the clustering reads reach Python: whole entities
        # would drag the ``source_meta`` JSONB blob along.
        gallery_stmt = (
            select(Gallery)
            .options(
                load_only(
                    Gallery.id,
                    Gallery.gid,
                    Gallery.title,
                    Gallery.title_jpn,
                    Gallery.file_size,
                    Gallery.page_count,
                    Gallery.file_count,
                    Gallery.category,
                    Gallery.storage_path,
                    Gallery.storage_type,
                    Gallery.token,
                )
            )
            .where(
                Gallery.expunged.is_(False),
                Gallery.trashed.is_(False),
                Gallery.gid.is_not(None),
            )
            .order_by(Gallery.id.asc())
        )
        gallery_rows = list((await session.scalars(gallery_stmt)).all())
        ids = [int(g.id) for g in gallery_rows]
        galleries = [_gallery_candidate(g) for g in gallery_rows]
        fav_repo = FavoritesRepository(session)
        tag_map = await _artist_tag_map(fav_repo, ids)

        fav_stmt = (
            select(FavoriteItem)
            .options(
                load_only(
                    FavoriteItem.gid,
                    FavoriteItem.title,
                    FavoriteItem.url,
                    FavoriteItem.token,
                    FavoriteItem.file_size,
                    FavoriteItem.thumb,
                    FavoriteItem.favcat,
                )
            )
            .order_by(FavoriteItem.gid.asc())
        )
        fav_rows = list((await session.scalars(fav_stmt)).all())
        fav_items = [
            {
                "gid": f.gid,
                "title": f.title,
                "url": f.url,
                "token": f.token,
                "file_size": f.file_size,
                "thumb": f.thumb,
                "favcat": f.favcat,
            }
            for f in fav_rows
        ]

        ignored_keys = await fav_repo.ignored_duplicate_keys()
        ignored = await fav_repo.ignored_duplicates()

    fav_gids = {int(f["gid"]) for f in fav_items if f["gid"] is not None}
    local_gids = {int(g["gid"]) for g in galleries if g["gid"] is not None}
    seen_fav_gids: set[int] = set()
    cloud_candidates: list[dict[str, Any]] = []
    for f in fav_items:
        if f["gid"] is None:
            continue
        gid = int(f["gid"])
        if gid in local_gids:
            continue
        if gid in seen_fav_gids:
            continue
        seen_fav_gids.add(gid)
        title = f["title"].strip() if f["title"] else ""
        if not title:
            continue
        cloud_category = f.get("category")
        cloud_favcat = f.get("favcat")
        cloud_candidates.append(
            {
                "gallery_id": None,
                "gid": gid,
                "title": title,
                "title_jpn": None,
                "url": f["url"],
                "token": f["token"],
                "file_size": f["file_size"],
                "thumb": f["thumb"],
                "favorited": True,
                "category": (
                    cloud_category
                    if isinstance(cloud_category, str) and cloud_category.strip()
                    else None
                ),
                "favcat": (
                    cloud_favcat
                    if isinstance(cloud_favcat, int) and not isinstance(cloud_favcat, bool)
                    else None
                ),
            }
        )

    all_candidates: list[Any] = list(galleries) + cloud_candidates
    # Clustering is pure CPU (0.23ms/gallery, 20s+ at 1e5); keep it off the
    # event loop that also serves HTTP and the scan worker.
    groups = await asyncio.to_thread(
        find_gallery_duplicate_groups,
        all_candidates,
        tag_map=tag_map,
        fav_gids=fav_gids,
    )

    ignored_gid_sets = [set(r.get("gids") or []) for r in ignored if r.get("gids")]
    filtered_groups = [
        g
        for g in groups
        if not duplicate_group_is_ignored(g, ignored_keys, ignored_gid_sets)
    ]

    try:
        from ..app.state import app_state

        app_state.cross_gid_duplicates = filtered_groups
    except Exception:  # noqa: BLE001, S110
        pass

    return filtered_groups


__all__ = [
    "DUP_CORE_MIN_EFFECTIVE_LEN",
    "DUP_SCORE_ARTIST_ONE_EMPTY",
    "DUP_SCORE_ARTIST_SAME",
    "DUP_SCORE_CORE_EXACT",
    "DUP_SCORE_THRESHOLD",
    "_CandidateItem",
    "_cluster_duplicate_candidates",
    "_core_effective_length",
    "artist_from_title",
    "calculate_duplicate_score",
    "cross_gid_scan_lock",
    "duplicate_group_is_ignored",
    "extract_duplicate_artist_and_core",
    "find_duplicate_groups",
    "find_gallery_duplicate_groups",
    "normalize_title",
    "scan_library_cross_gid_duplicates",
    "scan_library_cross_gid_duplicates_locked",
]
