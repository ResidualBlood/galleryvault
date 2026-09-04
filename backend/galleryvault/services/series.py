from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

from ..db.repositories.series import SeriesRepository
from .duplicates import normalize_title

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from ..db.models import Gallery, Series

logger = logging.getLogger(__name__)

# 打分常量（达 SCORE_THRESHOLD=50 连边）
SCORE_THRESHOLD = 50
SCORE_SERIES_BOTH = 40
SCORE_SERIES_SINGLE = 8
SCORE_ARTIST_SAME = 30
SCORE_ARTIST_ONE_EMPTY = 20
SCORE_GROUP_INTERSECT = 20
SCORE_PARODY_INTERSECT = 15
SCORE_CORE_EXACT = 35
SCORE_CORE_PREFIX = 20
CORE_MIN_EFFECTIVE_LEN = 6

PARODY_STOP_WORDS = frozenset({"original", "オリジナル", "western", "misc"})

_LEADING_EVENT_RE = re.compile(r"^\s*[\(（][^\)）]+[\)）]\s*")
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

    1. Repeatedly strip leading ()/（） event prefixes.
    2. Extract artist: inner of [Circle (Artist)] / [Artist]; else Artist - Title (-/–/—).
       Skip if inner matches C\\d+. artist="" if not found.
    3. Strip noise brackets whole-segment: 动态压缩版/动态版/无修/無修正/AI Generated/DL版.
    4. Strip trailing volume numbers attached to end of title (do not strip internal numbers).
    5. Strip trailing subtitle terms (e.g. 催眠編/前編/後編/中編/完結編/上巻/下巻).
    """
    cleaned = (raw or "").strip()

    # 1. 循环剥前导 ()/（） 活动前缀
    while True:
        m = _LEADING_EVENT_RE.match(cleaned)
        if not m:
            break
        rem = cleaned[m.end() :].strip()
        if not rem:
            break
        cleaned = rem

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
    """Compute single-gallery s::{artist}::{core} match key.

    Returns None if effective length of core < 6.
    """
    raw = title or title_jpn or ""
    if not raw.strip():
        return None
    artist, stripped = extract_artist_and_stripped_title(raw)
    core = normalize_title(stripped)
    if _core_effective_length(core) < CORE_MIN_EFFECTIVE_LEN:
        return None
    return f"s::{artist}::{core}"


class GalleryFeatures:
    """Features extracted from a gallery and its tags for series scoring."""

    def __init__(
        self,
        gallery: Gallery,
        tags: list[tuple[str, str]] | None = None,
    ) -> None:
        self.gallery = gallery
        self.id = gallery.id

        raw = gallery.title or gallery.title_jpn or ""
        parsed_artist, stripped = extract_artist_and_stripped_title(raw)
        self.parsed_artist = parsed_artist
        self.core = normalize_title(stripped)
        self.core_len = _core_effective_length(self.core)

        self.artists: set[str] = set()
        if parsed_artist:
            self.artists.add(parsed_artist)

        self.groups: set[str] = set()
        self.parodies: set[str] = set()
        self.has_series_tag: bool = False

        for ns, name in tags or []:
            ns_clean = ns.strip().lower()
            name_clean = name.strip().lower()
            if not name_clean:
                continue
            if ns_clean == "artist":
                self.artists.add(name_clean)
            elif ns_clean == "group":
                self.groups.add(name_clean)
            elif ns_clean == "parody":
                if name_clean not in PARODY_STOP_WORDS:
                    self.parodies.add(name_clean)
            elif ns_clean == "other" and name_clean == "multi-work series":
                self.has_series_tag = True


def calculate_series_score(
    f1: GalleryFeatures, f2: GalleryFeatures
) -> tuple[int, bool]:
    """Calculate similarity score between two galleries and determine edge validity.

    Returns (score, can_edge).
    """
    score = 0

    # 1. 系列标签
    if f1.has_series_tag and f2.has_series_tag:
        score += SCORE_SERIES_BOTH
    elif f1.has_series_tag or f2.has_series_tag:
        score += SCORE_SERIES_SINGLE

    # 2. 作者分（30 / 20 互斥）
    # 作者相同（解析或 artist: 交集）：30；与「一方无作者」20 互斥
    # 作者双方非空且无交集：作者分=0
    has_same_artist = False
    if f1.artists and f2.artists:
        if f1.artists & f2.artists:
            score += SCORE_ARTIST_SAME
            has_same_artist = True
        else:
            # 双方非空且无交集：作者分=0
            pass
    else:
        # 一方无作者（含双方均无作者）：20
        score += SCORE_ARTIST_ONE_EMPTY

    # 3. group: 交集
    has_same_group = bool(f1.groups and f2.groups and (f1.groups & f2.groups))
    if has_same_group:
        score += SCORE_GROUP_INTERSECT

    # 4. parody: 交集（停用 original/オリジナル/western/misc）
    if f1.parodies and f2.parodies and (f1.parodies & f2.parodies):
        score += SCORE_PARODY_INTERSECT

    # 5. core 精确与真前缀
    is_exact = False
    is_prefix = False

    if f1.core and f2.core:
        if f1.core == f2.core:
            if f1.core_len >= CORE_MIN_EFFECTIVE_LEN:
                is_exact = True
                score += SCORE_CORE_EXACT
        else:
            # 检查真前缀（非子串），且仅当作者相同或社团相同
            # 短 core 有效长度需 >= CORE_MIN_EFFECTIVE_LEN
            if (has_same_artist or has_same_group) and (
                (
                    len(f1.core) < len(f2.core)
                    and f2.core.startswith(f1.core)
                    and f1.core_len >= CORE_MIN_EFFECTIVE_LEN
                )
                or (
                    len(f2.core) < len(f1.core)
                    and f1.core.startswith(f2.core)
                    and f2.core_len >= CORE_MIN_EFFECTIVE_LEN
                )
            ):
                is_prefix = True
                score += SCORE_CORE_PREFIX

    # 条款：系列标签+同 parody 只对 exact 或真前缀补边。
    # 无作者/社团的前缀边禁止。
    can_edge = (is_exact or is_prefix) and score >= SCORE_THRESHOLD
    return score, can_edge


def compute_cluster_match_key(features: list[GalleryFeatures]) -> str:
    """Compute cluster match_key: s::{众数作者或空}::{簇内最短 core}."""
    valid_cores = [
        f.core for f in features if f.core and f.core_len >= CORE_MIN_EFFECTIVE_LEN
    ]
    if not valid_cores:
        valid_cores = [f.core for f in features if f.core]
    shortest_core = min(valid_cores, key=lambda c: (len(c), c)) if valid_cores else ""

    artist_counts: Counter[str] = Counter()
    for f in features:
        for a in f.artists:
            if a:
                artist_counts[a] += 1

    if artist_counts:
        mode_artist = min(artist_counts.items(), key=lambda x: (-x[1], x[0]))[0]
    else:
        mode_artist = ""

    return f"s::{mode_artist}::{shortest_core}"


class UnionFind:
    """Disjoint-set data structure with path compression and rank heuristic."""

    def __init__(self, elements: Iterable[int]) -> None:
        self.parent = {x: x for x in elements}
        self.rank = {x: 0 for x in elements}

    def find(self, x: int) -> int:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        curr = x
        while curr != root:
            nxt = self.parent[curr]
            self.parent[curr] = root
            curr = nxt
        return root

    def union(self, x: int, y: int) -> None:
        rx = self.find(x)
        ry = self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            self.parent[rx] = ry
        elif self.rank[rx] > self.rank[ry]:
            self.parent[ry] = rx
        else:
            self.parent[ry] = rx
            self.rank[rx] += 1


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
    """Rebuild all automatic series groups according to PLAN-系列打分:

    - Automatic groups (match_key is not None) are fully recalculated.
    - Candidates = unassigned galleries ∪ auto group members; exclude manual members & exclusions.
    - Tags fetched only for candidate galleries (filtered to artist/group/parody/other).
    - Blocking: artist / group / core.
    - Score threshold >= 50, edge only on exact core or true prefix with same artist/group.
    - Union-Find clustering, clusters with size >= 2 form automatic series.
    - Match key: s::{mode_artist}::{shortest_core}.
    - Series reuse: first member overlap, then match_key.
    - Empty auto series deleted (except name_manual rows).
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
            candidate_ids = [g.id for g in candidates]
            tag_map = await repo.get_tags_for_galleries(candidate_ids)

            features = {
                g.id: GalleryFeatures(g, tag_map.get(g.id, []))
                for g in candidates
            }

            # 阻塞（Blocking）：非空作者 / 非空 group / 精确 core
            artist_blocks: dict[str, list[int]] = defaultdict(list)
            group_blocks: dict[str, list[int]] = defaultdict(list)
            core_blocks: dict[str, list[int]] = defaultdict(list)

            for feat in features.values():
                for a in feat.artists:
                    if a:
                        artist_blocks[a].append(feat.id)
                for grp in feat.groups:
                    if grp:
                        group_blocks[grp].append(feat.id)
                if feat.core and feat.core_len >= CORE_MIN_EFFECTIVE_LEN:
                    core_blocks[feat.core].append(feat.id)

            candidate_pairs: set[tuple[int, int]] = set()
            for block in (artist_blocks, group_blocks, core_blocks):
                for gids in block.values():
                    if len(gids) >= 2:
                        for i in range(len(gids)):
                            for j in range(i + 1, len(gids)):
                                u, v = gids[i], gids[j]
                                if u > v:
                                    u, v = v, u
                                candidate_pairs.add((u, v))

            # 打分与并查集连边
            uf = UnionFind(candidate_ids)
            for u, v in candidate_pairs:
                _, can_edge = calculate_series_score(features[u], features[v])
                if can_edge:
                    uf.union(u, v)

            # 簇提取（size >= 2 成组）
            clusters_map: dict[int, list[GalleryFeatures]] = defaultdict(list)
            for gid in candidate_ids:
                root = uf.find(gid)
                clusters_map[root].append(features[gid])

            valid_clusters = [
                feats for feats in clusters_map.values() if len(feats) >= 2
            ]

            if auto_series_ids:
                await repo.clear_auto_series_items(auto_series_ids)

            cluster_data = []
            for feats in valid_clusters:
                glist = [f.gallery for f in feats]
                gids = {f.id for f in feats}
                mk = compute_cluster_match_key(feats)
                name = determine_group_name(glist)
                cluster_data.append(
                    {
                        "feats": feats,
                        "glist": glist,
                        "gids": gids,
                        "match_key": mk,
                        "name": name,
                    }
                )

            used_series_ids: set[int] = set()
            cluster_series_map: dict[int, Series] = {}

            # 复用：先成员重叠（Member Overlap）
            overlap_pairs = []
            for c_idx, c_info in enumerate(cluster_data):
                for s in auto_series:
                    old_gids = old_series_to_gids.get(s.id, set())
                    overlap = len(c_info["gids"] & old_gids)
                    if overlap > 0:
                        overlap_pairs.append((overlap, c_idx, s))

            overlap_pairs.sort(key=lambda x: x[0], reverse=True)
            for _, c_idx, s in overlap_pairs:
                if c_idx not in cluster_series_map and s.id not in used_series_ids:
                    cluster_series_map[c_idx] = s
                    used_series_ids.add(s.id)

            # 复用：后 match_key
            for c_idx, c_info in enumerate(cluster_data):
                if c_idx in cluster_series_map:
                    continue
                for s in auto_series:
                    if s.id not in used_series_ids and s.match_key == c_info["match_key"]:
                        cluster_series_map[c_idx] = s
                        used_series_ids.add(s.id)
                        break

            created_count = 0
            merged_count = 0
            assigned_match_keys: set[str] = set()

            for c_idx, c_info in enumerate(cluster_data):
                base_mk = c_info["match_key"]
                mk = base_mk
                suffix = 2
                while mk in assigned_match_keys:
                    mk = f"{base_mk}::{suffix}"
                    suffix += 1
                assigned_match_keys.add(mk)

                if c_idx in cluster_series_map:
                    target_series = cluster_series_map[c_idx]
                    target_series.match_key = mk
                    if not target_series.name_manual:
                        target_series.name = c_info["name"]
                else:
                    target_series = await repo.create(
                        name=c_info["name"], match_key=mk, name_manual=False
                    )
                    cluster_series_map[c_idx] = target_series
                    used_series_ids.add(target_series.id)
                    created_count += 1

                await repo.add_items(
                    target_series.id, [f.id for f in c_info["feats"]], source="auto"
                )
                merged_count += len(c_info["feats"])

            # 清理未使用的已有 auto series
            for s in auto_series:
                if s.id not in used_series_ids:
                    if not s.name_manual:
                        await repo.delete_series(s.id)
                    else:
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
