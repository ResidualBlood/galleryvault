from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import TYPE_CHECKING

from ..db.repositories.series import SeriesRepository
from .duplicates import normalize_title

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from ..db.models import Gallery, Series

logger = logging.getLogger(__name__)

_LEADING_EVENT_RE = re.compile(r"^(?:\s*\([cC]\d+\))+\s*")
_NOISE_BRACKETS_RE = re.compile(
    r"[\(\[\{（【［][^\)\]\}）】］]*(?:"
    r"动态压缩版|动态版|无修|無修正|AI\s*Generated|DL\s*版"
    r")[^\)\]\}）】］]*[\)\]\}）】］]",
    re.IGNORECASE,
)
_VOL_SUFFIX_RE = re.compile(
    r"(?:\s*(?:vol\.?|volume|v|ch\.?|chapter|ep\.?|第)\s*\d+(?:\s*[巻卷话話期])?|\s*\d+(?:[巻卷话話期])?|\s*\d+)\s*$",
    re.IGNORECASE,
)
_SUBTITLE_SUFFIX_RE = re.compile(
    r"\s*(?:催眠[編编]|前[編编]|[後后][編编]|中[編编]|完[結结][編编]|上[巻卷]|下[巻卷])\s*$"
)


def _core_effective_length(core: str) -> int:
    """Calculate effective length where CJK characters count as 2 and ASCII counts as 1."""
    return sum(
        2 if ("\u3040" <= ch <= "\u30ff" or "\u3400" <= ch <= "\u9fff") else 1
        for ch in core
    )


def extract_artist_and_stripped_title(raw: str) -> tuple[str, str]:
    """Parse raw title according to PLAN-系列匹配:

    1. Strip leading (C\\d+) and whitespace.
    2. Extract artist: inner of [Circle (Artist)] / [Artist]; else Artist - Title (-/–/—).
       Skip if inner matches C\\d+. artist="" if not found.
    3. Strip noise brackets whole-segment: 动态压缩版/动态版/无修/無修正/AI Generated/DL版.
    4. Strip trailing volume numbers attached to end of title (do not strip internal numbers).
    5. Strip trailing subtitle terms (e.g. 催眠編/前編/後編/中編/完結編/上巻/下巻).
    """
    # 1. 剥前导 (C\d+)
    cleaned = _LEADING_EVENT_RE.sub("", raw or "").strip()

    # 2. 作者
    artist = ""
    while True:
        m = re.match(r"^\s*\[([^\]]+)\]\s*", cleaned)
        if not m:
            break
        inner = m.group(1).strip()
        cleaned = cleaned[m.end() :].strip()
        # 内层若是 C\d+ 则跳过再找
        if re.fullmatch(r"[cC]\d+", inner):
            continue
        sub = re.search(r"\(([^)]+)\)", inner)
        cand = sub.group(1).strip() if sub else inner
        if cand:
            artist = cand.lower()
            break

    if not artist:
        m_dash = re.match(r"^\s*([^-–—]+?)\s*[-–—]\s*(.+)$", cleaned)
        if m_dash:
            artist = m_dash.group(1).strip().lower()
            cleaned = m_dash.group(2).strip()

    # 3. 噪声括号整段删（宁少勿滥）
    cleaned = _NOISE_BRACKETS_RE.sub(" ", cleaned).strip()

    # 4. 卷号：删末尾及紧贴书名末字的卷号
    cleaned = _VOL_SUFFIX_RE.sub("", cleaned).strip()

    # 5. 核心末尾整词副标题（可无空格）
    cleaned = _SUBTITLE_SUFFIX_RE.sub("", cleaned).strip()

    # 若副标题移除后末尾显露出卷号，再清一次末尾卷号
    cleaned = _VOL_SUFFIX_RE.sub("", cleaned).strip()

    return artist, cleaned


def compute_series_key(title: str | None, title_jpn: str | None) -> str:
    """Normalize title after stripping event, artist, noise, volume, and subtitle."""
    raw = title or title_jpn or ""
    _, stripped = extract_artist_and_stripped_title(raw)
    return normalize_title(stripped)


def compute_match_key(title: str | None, title_jpn: str | None) -> str | None:
    """Compute {artist}::{core} match key string.

    Returns None if effective length of core < 6.
    """
    raw = title or title_jpn or ""
    if not raw.strip():
        return None
    artist, stripped = extract_artist_and_stripped_title(raw)
    core = normalize_title(stripped)
    if _core_effective_length(core) < 6:
        return None
    return f"{artist}::{core}"


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
    """Rebuild all automatic series groups according to PLAN:

    - Automatic groups (match_key is not None) are fully recalculated.
    - Candidates = unassigned galleries ∪ auto group members; exclude manual members & exclusions.
    - Groups with len >= 2 form automatic series.
    - Manual series (match_key is None) are completely untouched.
    - Reused or matched series with name_manual=True retain their custom name.
    - Empty auto series are deleted (except name_manual rows which keep their record).
    """
    if session_factory is None:
        from ..app.state import app_state

        session_factory = app_state.session_factory
    if not session_factory:
        return {"created": 0, "merged": 0}

    try:
        async with session_factory() as session, session.begin():
            repo = SeriesRepository(session)
            auto_series = await repo.get_auto_series()
            auto_series_ids = [s.id for s in auto_series]
            old_series_to_gids = await repo.get_auto_series_gids(auto_series_ids)

            candidates = await repo.get_rebuild_candidate_galleries()

            grouped_candidates: dict[str, list[Gallery]] = defaultdict(list)
            for g in candidates:
                mk = compute_match_key(g.title, g.title_jpn)
                if not mk:
                    continue
                grouped_candidates[mk].append(g)

            valid_groups = {
                mk: glist
                for mk, glist in grouped_candidates.items()
                if len(glist) >= 2
            }

            if auto_series_ids:
                await repo.clear_auto_series_items(auto_series_ids)

            used_series_ids: set[int] = set()
            new_series_map: dict[str, Series] = {}

            # Match existing auto series by exact match_key first
            auto_by_key = {s.match_key: s for s in auto_series if s.match_key}
            for mk in valid_groups:
                if mk in auto_by_key and auto_by_key[mk].id not in used_series_ids:
                    s = auto_by_key[mk]
                    new_series_map[mk] = s
                    used_series_ids.add(s.id)

            # Match unmapped name_manual series by overlapping members
            unmapped_name_manual = [
                s
                for s in auto_series
                if s.name_manual and s.id not in used_series_ids
            ]
            for s in unmapped_name_manual:
                old_gids = old_series_to_gids.get(s.id, set())
                best_mk: str | None = None
                best_overlap = 0
                for mk, glist in valid_groups.items():
                    if mk in new_series_map:
                        continue
                    overlap = len(old_gids & {g.id for g in glist})
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_mk = mk
                if best_mk is not None and best_overlap > 0:
                    s.match_key = best_mk
                    new_series_map[best_mk] = s
                    used_series_ids.add(s.id)

            created_count = 0
            merged_count = 0

            for mk, glist in valid_groups.items():
                if mk in new_series_map:
                    target_series = new_series_map[mk]
                    target_series.match_key = mk
                    if not target_series.name_manual:
                        target_series.name = determine_group_name(glist)
                else:
                    name = determine_group_name(glist)
                    target_series = await repo.create(
                        name=name, match_key=mk, name_manual=False
                    )
                    new_series_map[mk] = target_series
                    created_count += 1

                await repo.add_items(
                    target_series.id, [g.id for g in glist], source="auto"
                )
                merged_count += len(glist)

            # Clean up remaining unused auto series
            for s in auto_series:
                if s.id not in used_series_ids:
                    if not s.name_manual:
                        await repo.delete_series(s.id)
                    else:
                        # Clear match_key to avoid unique constraint collisions
                        if (
                            s.match_key
                            and s.match_key in valid_groups
                            and new_series_map.get(s.match_key) != s
                        ):
                            s.match_key = None

            logger.info(
                "series rebuild complete",
                extra={
                    "groups_created": created_count,
                    "galleries_merged": merged_count,
                },
            )
            return {"created": created_count, "merged": merged_count}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "series rebuild failed",
            extra={"error": type(exc).__name__, "detail": str(exc)},
        )
        return {"created": 0, "merged": 0}
