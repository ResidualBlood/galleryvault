from __future__ import annotations

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

    from ..db.models import FavoriteItem, Gallery
    from ..db.repository import FavoritesRepository

    async with session_factory() as session:
        stmt = (
            select(Gallery)
            .where(
                Gallery.expunged.is_(False),
                Gallery.trashed.is_(False),
                Gallery.gid.is_not(None),
            )
            .order_by(Gallery.id.asc())
        )
        galleries = list((await session.scalars(stmt)).all())
        ids = [g.id for g in galleries]
        fav_repo = FavoritesRepository(session)
        tag_map = await fav_repo.tags_for_gallery_ids(ids)

        fav_stmt = select(FavoriteItem).order_by(FavoriteItem.gid.asc())
        fav_items = list((await session.scalars(fav_stmt)).all())

        ignored_keys = await fav_repo.ignored_duplicate_keys()
        ignored = await fav_repo.ignored_duplicates()

    fav_gids = {int(f.gid) for f in fav_items if f.gid is not None}
    local_gids = {int(g.gid) for g in galleries if g.gid is not None}
    seen_fav_gids: set[int] = set()
    cloud_candidates: list[dict[str, Any]] = []
    for f in fav_items:
        if f.gid is None:
            continue
        gid = int(f.gid)
        if gid in local_gids:
            continue
        if gid in seen_fav_gids:
            continue
        seen_fav_gids.add(gid)
        title = f.title.strip() if f.title else ""
        if not title:
            continue
        cloud_category = getattr(f, "category", None)
        cloud_favcat = getattr(f, "favcat", None)
        cloud_candidates.append(
            {
                "gallery_id": None,
                "gid": gid,
                "title": title,
                "title_jpn": None,
                "url": f.url,
                "token": f.token,
                "file_size": f.file_size,
                "thumb": f.thumb,
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
    groups = find_gallery_duplicate_groups(
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
    "duplicate_group_is_ignored",
    "extract_duplicate_artist_and_core",
    "find_duplicate_groups",
    "find_gallery_duplicate_groups",
    "normalize_title",
    "scan_library_cross_gid_duplicates",
]
