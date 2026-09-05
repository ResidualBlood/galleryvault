from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

DUP_SCORE_THRESHOLD = 50
DUP_SCORE_ARTIST_SAME = 30
DUP_SCORE_ARTIST_ONE_EMPTY = 20
DUP_SCORE_CORE_EXACT = 35
DUP_CORE_MIN_EFFECTIVE_LEN = 6

_VERSION_TAG = re.compile(r"\[([^\]]*)\]")
_BRACKETED = re.compile(r"[\[\]()【】（）]")
_GROUP_LEAD = re.compile(r"^\s*(?:\[([^\]]*)\]|\(([^)]*)\))\s*")

_LEADING_EVENT_RE = re.compile(r"^\s*[\(（][^\)）]+[\)）]\s*")
_NOISE_BRACKETS_RE = re.compile(
    r"[\(\[\{（【［][^\)\]\}）】］]*(?:"
    r"动态压缩版|动态版|无修|無修正|AI\s*Generated|DL\s*版"
    r")[^\)\]\}）】］]*[\)\]\}）】］]",
    re.IGNORECASE,
)


def _core_effective_length(core: str) -> int:
    """Calculate effective length where CJK characters count as 2 and ASCII counts as 1."""
    return sum(
        2 if ("\u3040" <= ch <= "\u30ff" or "\u3400" <= ch <= "\u9fff") else 1
        for ch in core
    )


def normalize_title(title: str) -> str:
    """Lowercase, drop everything non-alphanumeric (CJK kept), strip spaces.

    Version markers like ``[DL版]``/``[無修正]`` live inside brackets that are
    removed, so different versions of the same work collapse onto one key.
    """
    value = _VERSION_TAG.sub(" ", title or "")
    value = _BRACKETED.sub(" ", value)
    return re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff]+", "", value.lower())


def artist_from_title(title: str) -> str | None:
    """Best-effort artist extraction from an ExHentai-style title.

    Handles ``[Circle (Artist)]``, ``[Artist]`` and ``(Artist)`` leading forms.
    """
    lead = _GROUP_LEAD.match(title or "")
    if not lead:
        return None
    inner = (lead.group(1) or lead.group(2) or "").strip()
    if not inner:
        return None
    paren = re.search(r"\(([^)]+)\)", inner)
    return (paren.group(1) if paren else inner).strip().lower() or None


def extract_duplicate_artist_and_core(
    raw: str, gid: int | None = None
) -> tuple[str, str, list[str]]:
    """Extract artist, primary core, and alt_cores from raw title.

    1. DUP-STRIP-GIDPREFIX: If gid is provided and raw starts with {gid}- or {gid}_, strip it.
    2. Repeatedly strip leading ()/（） event prefixes.
    3. Extract artist: inner of [Circle (Artist)] / [Artist]; else Artist - Title.
       Skip if inner matches C\\d+.
    4. Strip noise brackets whole-segment (动态压缩版/动态版/无修/無修正/AI Generated/DL版).
       Do NOT strip volume numbers or subtitles.
    5. DUP-PAREN-ALT: extract alt_cores from any (...) / （...） in remainder (effective len >= 6).
    6. Return (artist, primary_core, alt_cores).
    """
    cleaned = (raw or "").strip()

    if gid is not None:
        gid_dash = f"{gid}-"
        gid_under = f"{gid}_"
        if cleaned.startswith(gid_dash):
            cleaned = cleaned[len(gid_dash) :].strip()
        elif cleaned.startswith(gid_under):
            cleaned = cleaned[len(gid_under) :].strip()

    while True:
        m = _LEADING_EVENT_RE.match(cleaned)
        if not m:
            break
        rem = cleaned[m.end() :].strip()
        if not rem:
            break
        cleaned = rem

    artist = ""
    while True:
        m = re.match(r"^\s*\[([^\]]+)\]\s*", cleaned)
        if not m:
            break
        inner = m.group(1).strip()
        cleaned = cleaned[m.end() :].strip()
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

    cleaned = _NOISE_BRACKETS_RE.sub(" ", cleaned).strip()

    alt_cores: list[str] = []
    for m in re.finditer(r"[\(（]([^\)）]+)[\)）]", cleaned):
        inner = m.group(1).strip()
        alt_norm = normalize_title(inner)
        if (
            _core_effective_length(alt_norm) >= DUP_CORE_MIN_EFFECTIVE_LEN
            and alt_norm not in alt_cores
        ):
            alt_cores.append(alt_norm)

    primary_core = normalize_title(cleaned)
    alt_cores = [c for c in alt_cores if c != primary_core]
    return artist, primary_core, alt_cores


def calculate_duplicate_score(
    a: dict[str, Any],
    b: dict[str, Any],
) -> tuple[int, bool]:
    """Calculate duplicate score and whether an edge can be formed.

    Returns (score, can_edge).
    """
    artists_a = a.get("artists")
    if artists_a is None:
        art = a.get("artist")
        artists_a = {str(art).lower()} if art else set()
    else:
        artists_a = {str(x).lower() for x in artists_a if x}

    artists_b = b.get("artists")
    if artists_b is None:
        art = b.get("artist")
        artists_b = {str(art).lower()} if art else set()
    else:
        artists_b = {str(x).lower() for x in artists_b if x}

    score = 0
    if not artists_a or not artists_b:
        score += DUP_SCORE_ARTIST_ONE_EMPTY
    elif artists_a & artists_b:
        score += DUP_SCORE_ARTIST_SAME

    core_a = a.get("core", "")
    core_b = b.get("core", "")
    len_a = a.get("core_len", _core_effective_length(core_a))
    len_b = b.get("core_len", _core_effective_length(core_b))

    exact = bool(
        core_a
        and core_a == core_b
        and len_a >= DUP_CORE_MIN_EFFECTIVE_LEN
        and len_b >= DUP_CORE_MIN_EFFECTIVE_LEN
    )
    if exact:
        score += DUP_SCORE_CORE_EXACT

    can_edge = bool(exact and score >= DUP_SCORE_THRESHOLD)
    return score, can_edge


def duplicate_group_is_ignored(
    group: dict[str, Any],
    ignored_keys: set[str] | Iterable[str],
    ignored_gid_sets: list[set[int]] | Iterable[set[int]] | None = None,
) -> bool:
    """Check if a duplicate group is ignored by key, legacy_keys, or gid subset."""
    ignored_keys_set = (
        set(ignored_keys) if not isinstance(ignored_keys, set) else ignored_keys
    )
    group_key = group.get("key", "")
    if group_key in ignored_keys_set:
        return True

    legacy_keys = group.get("legacy_keys") or []
    if any(k in ignored_keys_set for k in legacy_keys):
        return True

    items = group.get("items") or []
    group_gids = {it["gid"] for it in items if "gid" in it}
    if not group_gids:
        return False

    if ignored_gid_sets:
        for ig_gids in ignored_gid_sets:
            if ig_gids and group_gids.issubset(ig_gids):
                return True

    return False


class _CandidateItem:
    def __init__(
        self,
        gid: int,
        item_dict: dict[str, Any],
        primary_cores: set[str],
        alt_cores: set[str],
        parsed_artist: str | None,
        artists: set[str],
        legacy_keys: list[str],
    ):
        self.gid = gid
        self.item_dict = item_dict
        self.primary_cores = primary_cores
        self.alt_cores = alt_cores
        self.parsed_artist = parsed_artist
        self.artists = artists
        self.legacy_keys = legacy_keys


def _cluster_duplicate_candidates(candidates: list[_CandidateItem]) -> list[dict[str, Any]]:
    buckets: dict[str, list[tuple[_CandidateItem, bool]]] = defaultdict(list)
    for cand in candidates:
        for pri in cand.primary_cores:
            buckets[pri].append((cand, True))
        for alt in cand.alt_cores:
            buckets[alt].append((cand, False))

    raw_groups: list[dict[str, Any]] = []

    for core, bucket_items in buckets.items():
        if not any(is_pri for _, is_pri in bucket_items):
            continue

        seen_gids: set[int] = set()
        unique_items: list[tuple[_CandidateItem, bool]] = []
        for cand, is_pri in bucket_items:
            if cand.gid not in seen_gids:
                seen_gids.add(cand.gid)
                unique_items.append((cand, is_pri))

        if len(seen_gids) < 2:
            continue

        all_artists = set().union(*(c.artists for c, _ in unique_items))
        if len(all_artists) <= 1:
            cands = [c for c, _ in unique_items]
            mode_artist = ""
            if all_artists:
                target_art = next(iter(all_artists))
                parsed = [
                    c.parsed_artist
                    for c in cands
                    if c.parsed_artist and c.parsed_artist.lower() == target_art
                ]
                mode_artist = parsed[0] if parsed else target_art
            if len({c.gid for c in cands}) >= 2 and any(is_pri for _, is_pri in unique_items):
                raw_groups.append(
                    {
                        "core": core,
                        "mode_artist": mode_artist,
                        "candidates": cands,
                    }
                )
        else:
            for art in sorted(all_artists):
                sub_items = [(c, is_pri) for c, is_pri in unique_items if art in c.artists]
                sub_gids = {c.gid for c, _ in sub_items}
                if len(sub_gids) >= 2 and any(is_pri for _, is_pri in sub_items):
                    sub_cands = [c for c, _ in sub_items]
                    parsed = [
                        c.parsed_artist
                        for c in sub_cands
                        if c.parsed_artist and c.parsed_artist.lower() == art
                    ]
                    mode_artist = parsed[0] if parsed else art
                    raw_groups.append(
                        {
                            "core": core,
                            "mode_artist": mode_artist,
                            "candidates": sub_cands,
                        }
                    )
            empty_items = [(c, is_pri) for c, is_pri in unique_items if not c.artists]
            empty_gids = {c.gid for c, _ in empty_items}
            if len(empty_gids) >= 2 and any(is_pri for _, is_pri in empty_items):
                raw_groups.append(
                    {
                        "core": core,
                        "mode_artist": "",
                        "candidates": [c for c, _ in empty_items],
                    }
                )

    final_groups_map: dict[frozenset[int], dict[str, Any]] = {}
    for rg in raw_groups:
        gid_set = frozenset(c.gid for c in rg["candidates"])
        existing = final_groups_map.get(gid_set)
        if existing is None:
            final_groups_map[gid_set] = rg
        else:
            score_new = (1 if rg["mode_artist"] else 0, len(rg["core"]))
            score_old = (1 if existing["mode_artist"] else 0, len(existing["core"]))
            if score_new > score_old:
                final_groups_map[gid_set] = rg

    result_groups: list[dict[str, Any]] = []
    for rg in final_groups_map.values():
        mode_artist = rg["mode_artist"]
        core = rg["core"]
        items = [c.item_dict for c in rg["candidates"]]
        items.sort(key=lambda e: (e.get("title") or "", e.get("gid", 0)))
        legacy_keys = sorted({k for c in rg["candidates"] for k in c.legacy_keys})
        result_groups.append(
            {
                "key": f"{mode_artist}|{core}",
                "artist": mode_artist or None,
                "items": items,
                "legacy_keys": legacy_keys,
            }
        )

    result_groups.sort(key=lambda g: (-len(g["items"]), (g["items"][0].get("title") or "")))
    return result_groups


def find_duplicate_groups(
    items: list[tuple[int, int, str, str, str, int | None, int | None, object, object]],
    *,
    gallery_titles: dict[int, tuple[str | None, str | None]],
    tag_map: dict[int, list[tuple[str, str]]] | None = None,
) -> list[dict[str, Any]]:
    """Group favorite items that are likely the same work in different versions.

    ``items`` is ``(favcat, gid, token, title, url, gallery_id, file_size,
    first_seen_at, posted_at)``. Titles are taken from the favorite record,
    falling back to the local gallery's English then Japanese title. Items
    with no usable title are skipped.
    """
    candidates: list[_CandidateItem] = []
    for favcat, gid, token, title, url, gallery_id, file_size, first_seen_at, posted_at in items:
        eff_title = title
        if not eff_title and gallery_id is not None:
            en, jp = gallery_titles.get(gid, (None, None))
            eff_title = en or jp or ""
        if not eff_title:
            continue

        legacy_key = f"{artist_from_title(eff_title) or ''}|{normalize_title(eff_title)}"
        parsed_artist, pri_core, alt_cores = extract_duplicate_artist_and_core(eff_title, gid=gid)

        artists: set[str] = set()
        if parsed_artist:
            artists.add(parsed_artist)
        if tag_map and gallery_id is not None:
            for ns, name in tag_map.get(gallery_id, []):
                if ns and ns.lower() == "artist" and name:
                    artists.add(name.lower())

        primary_cores: set[str] = set()
        if _core_effective_length(pri_core) >= DUP_CORE_MIN_EFFECTIVE_LEN:
            primary_cores.add(pri_core)

        alt_cores_set: set[str] = {
            c
            for c in alt_cores
            if _core_effective_length(c) >= DUP_CORE_MIN_EFFECTIVE_LEN and c != pri_core
        }

        if not primary_cores and not alt_cores_set:
            continue

        item_dict = {
            "favcat": favcat,
            "gid": gid,
            "token": token,
            "title": eff_title,
            "url": url,
            "gallery_id": gallery_id,
            "file_size": file_size,
            "first_seen_at": first_seen_at,
            "posted_at": posted_at,
        }

        candidates.append(
            _CandidateItem(
                gid=gid,
                item_dict=item_dict,
                primary_cores=primary_cores,
                alt_cores=alt_cores_set,
                parsed_artist=parsed_artist or None,
                artists=artists,
                legacy_keys=[legacy_key],
            )
        )

    return _cluster_duplicate_candidates(candidates)


def find_gallery_duplicate_groups(
    galleries: list[Any],
    *,
    tag_map: dict[int, list[tuple[str, str]]] | None = None,
) -> list[dict[str, Any]]:
    """Group library galleries across gids that are likely the same work in different versions.

    Implements OPT-LIB-XGID:
    - Dual raw titles: title and title_jpn
    - Cores union + tag_map artist
    """
    candidates: list[_CandidateItem] = []
    for g in galleries:
        gid = getattr(g, "gid", None) if not isinstance(g, dict) else g.get("gid")
        if gid is None:
            continue
        gallery_id = (
            getattr(g, "id", None)
            if not isinstance(g, dict)
            else g.get("id", g.get("gallery_id"))
        )
        title = getattr(g, "title", None) if not isinstance(g, dict) else g.get("title")
        title_jpn = (
            getattr(g, "title_jpn", None) if not isinstance(g, dict) else g.get("title_jpn")
        )
        file_size = (
            getattr(g, "file_size", None) if not isinstance(g, dict) else g.get("file_size")
        )
        pages = getattr(g, "pages", None) if not isinstance(g, dict) else g.get("pages")
        storage_path = (
            getattr(g, "storage_path", None)
            if not isinstance(g, dict)
            else g.get("storage_path")
        )
        storage_type = (
            getattr(g, "storage_type", None)
            if not isinstance(g, dict)
            else g.get("storage_type")
        )

        raws: list[str] = []
        if title and str(title).strip():
            raws.append(str(title).strip())
        if title_jpn and str(title_jpn).strip() and str(title_jpn).strip() not in raws:
            raws.append(str(title_jpn).strip())
        if not raws:
            continue

        artists: set[str] = set()
        primary_cores: set[str] = set()
        alt_cores_set: set[str] = set()
        legacy_keys: list[str] = []
        first_parsed_artist: str | None = None

        for raw in raws:
            legacy_keys.append(f"{artist_from_title(raw) or ''}|{normalize_title(raw)}")
            parsed_artist, pri_core, alts = extract_duplicate_artist_and_core(raw, gid=gid)
            if parsed_artist:
                artists.add(parsed_artist)
                if not first_parsed_artist:
                    first_parsed_artist = parsed_artist
            if _core_effective_length(pri_core) >= DUP_CORE_MIN_EFFECTIVE_LEN:
                primary_cores.add(pri_core)
            for alt in alts:
                if _core_effective_length(alt) >= DUP_CORE_MIN_EFFECTIVE_LEN:
                    alt_cores_set.add(alt)

        alt_cores_set -= primary_cores

        if tag_map and gallery_id is not None:
            for ns, name in tag_map.get(gallery_id, []):
                if ns and ns.lower() == "artist" and name:
                    artists.add(name.lower())

        if not primary_cores and not alt_cores_set:
            continue

        item_dict = {
            "gallery_id": gallery_id,
            "gid": gid,
            "title": title or title_jpn or f"gid {gid}",
            "title_jpn": title_jpn,
            "file_size": file_size,
            "pages": pages,
            "storage_path": storage_path,
            "storage_type": storage_type,
        }

        candidates.append(
            _CandidateItem(
                gid=gid,
                item_dict=item_dict,
                primary_cores=primary_cores,
                alt_cores=alt_cores_set,
                parsed_artist=first_parsed_artist,
                artists=artists,
                legacy_keys=legacy_keys,
            )
        )

    return _cluster_duplicate_candidates(candidates)


async def scan_library_cross_gid_duplicates(
    session_factory: Any = None,
) -> list[dict[str, Any]]:
    """Scan library galleries across gids and cache result in app_state."""
    if session_factory is None:
        from ..app.state import app_state

        session_factory = app_state.session_factory
    if not session_factory:
        return []

    from sqlalchemy import select

    from ..db.models import Gallery
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
        tag_map = await FavoritesRepository(session).tags_for_gallery_ids(ids)
        groups = find_gallery_duplicate_groups(galleries, tag_map=tag_map)

    try:
        from ..app.state import app_state

        app_state.cross_gid_duplicates = groups
    except Exception:  # noqa: BLE001, S110
        pass

    return groups
