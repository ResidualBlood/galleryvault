from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

_VERSION_TAG = re.compile(r"\[([^\]]*)\]")
_BRACKETED = re.compile(r"[\[\]()【】（）]")
_GROUP_LEAD = re.compile(r"^\s*(?:\[([^\]]*)\]|\(([^)]*)\))\s*")


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


def find_duplicate_groups(
    items: list[tuple[int, int, str, str, str, int | None, int | None, object]],
    *,
    gallery_titles: dict[int, tuple[str | None, str | None]],
) -> list[dict[str, Any]]:
    """Group favorite items that are likely the same work in different versions.

    ``items`` is ``(favcat, gid, token, title, url, gallery_id, file_size,
    first_seen_at)``.  Titles are taken from the favorite record, falling back
    to the local gallery's English then Japanese title.  Items with no usable
    title are skipped.

    A group requires a matching (normalized title, artist) pair with at least
    two distinct gallery ids.
    """
    keyed: dict[tuple[str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for favcat, gid, token, title, url, gallery_id, file_size, first_seen_at in items:
        eff_title = title
        if not eff_title and gallery_id is not None:
            en, jp = gallery_titles.get(gid, (None, None))
            eff_title = en or jp or ""
        if not eff_title:
            continue
        norm = normalize_title(eff_title)
        if len(norm) < 6:
            continue
        artist = artist_from_title(eff_title)
        keyed[(norm, artist)].append(
            {
                "favcat": favcat,
                "gid": gid,
                "token": token,
                "title": eff_title,
                "url": url,
                "gallery_id": gallery_id,
                "file_size": file_size,
                "first_seen_at": first_seen_at,
            }
        )
    groups = []
    for (norm, artist), entries in keyed.items():
        gids = {e["gid"] for e in entries}
        if len(gids) < 2:
            continue
        entries.sort(key=lambda e: (e["title"], e["gid"]))
        groups.append(
            {
                "key": f"{artist or ''}|{norm}",
                "artist": artist,
                "items": entries,
            }
        )
    groups.sort(key=lambda g: (-len(g["items"]), g["items"][0]["title"]))
    return groups
