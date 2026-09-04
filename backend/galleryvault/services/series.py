from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import TYPE_CHECKING

from ..db.repositories.series import SeriesRepository
from .duplicates import artist_from_title, normalize_title

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from ..db.models import Gallery

logger = logging.getLogger(__name__)


def compute_series_key(title: str | None, title_jpn: str | None) -> str:
    """Normalize title and strip trailing digits."""
    raw = title or title_jpn or ""
    norm = normalize_title(raw)
    return re.sub(r"\d+$", "", norm)


def compute_match_key(title: str | None, title_jpn: str | None) -> str | None:
    """Compute (series_key, artist_from_title) match key string.

    Returns None if len(series_key) < 6.
    """
    series_key = compute_series_key(title, title_jpn)
    if len(series_key) < 6:
        return None
    raw = title or title_jpn or ""
    artist = artist_from_title(raw)
    return f"{artist or ''}::{series_key}"


def determine_group_name(galleries: list[Gallery]) -> str:
    """Determine group name from shortest title/title_jpn with trailing digits removed."""
    candidates: list[str] = []
    for g in galleries:
        for t in (g.title, g.title_jpn):
            if t and t.strip():
                candidates.append(t.strip())
    if not candidates:
        return "Series"
    shortest = min(candidates, key=len)
    cleaned = re.sub(r"\s*\d+\s*$", "", shortest).strip()
    return cleaned or shortest


async def rebuild_series_groups(
    session_factory: async_sessionmaker | None = None,
) -> dict[str, int]:
    """Rebuild/merge series groups for unassigned galleries not in exclusions."""
    if session_factory is None:
        from ..app.state import app_state

        session_factory = app_state.session_factory
    if not session_factory:
        return {"created": 0, "merged": 0}

    try:
        async with session_factory() as session, session.begin():
            repo = SeriesRepository(session)
            existing_groups = await repo.get_existing_auto_groups()
            unassigned = await repo.get_unassigned_galleries()

            grouped_candidates: dict[str, list[Gallery]] = defaultdict(list)
            for g in unassigned:
                mk = compute_match_key(g.title, g.title_jpn)
                if not mk:
                    continue
                grouped_candidates[mk].append(g)

            created_count = 0
            merged_count = 0

            for mk, glist in grouped_candidates.items():
                if mk in existing_groups:
                    target_series = existing_groups[mk]
                    await repo.add_items(target_series.id, [g.id for g in glist], source="auto")
                    merged_count += len(glist)
                else:
                    if len(glist) >= 2:
                        name = determine_group_name(glist)
                        new_series = await repo.create(name=name, match_key=mk, name_manual=False)
                        await repo.add_items(new_series.id, [g.id for g in glist], source="auto")
                        existing_groups[mk] = new_series
                        created_count += 1

            logger.info(
                "series rebuild complete",
                extra={"groups_created": created_count, "galleries_merged": merged_count},
            )
            return {"created": created_count, "merged": merged_count}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "series rebuild failed",
            extra={"error": type(exc).__name__, "detail": str(exc)},
        )
        return {"created": 0, "merged": 0}
