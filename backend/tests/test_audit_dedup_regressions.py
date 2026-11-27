"""T12: regressions for gallery-dedup 0.2.0, exercised via the backend re-export.

Covers the audit findings that motivated the bump (audit dedup-grouping.md §7.1,
§7.2, §7.3, §7.4):

* leading noise brackets (``[DL版]``/``[中国翻訳]``/``[English]``/``【DL版】``) must
  not be parsed as an artist, so a noise-prefixed copy still groups with its
  canonical copy;
* Hangul (and full-width) titles must survive normalisation instead of
  silently dropping the gallery out of dedup;
* cross-language copies (English vs. Japanese) still do not group; 0.2.0 only
  fixes feature extraction, ``parent_gid`` is not consumed yet;
* a gallery referenced by several title cores lands in exactly one group
  (union-find closure), never in two.
"""

from __future__ import annotations

import pytest

from galleryvault.services.duplicates import (
    _core_effective_length,
    extract_duplicate_artist_and_core,
    find_duplicate_groups,
    find_gallery_duplicate_groups,
    normalize_title,
)


def _fav(
    gid: int, title: str, gallery_id: int | None = None
) -> tuple[int, int, str, str, str, int | None, int | None, object, object]:
    return (1, gid, f"tok{gid}", title, "", gallery_id, 1000, None, None)


@pytest.mark.parametrize(
    "noise",
    ["[DL版]", "[無修正]", "[中国翻訳]", "[English]", "【DL版】"],
)
def test_leading_noise_bracket_is_not_an_artist(noise: str) -> None:
    """§7.1: ``[DL版] X`` yields no artist and the core of ``X``."""
    artist, core, alt_cores = extract_duplicate_artist_and_core(f"{noise} Secret Story")
    assert artist == ""
    assert core == "secretstory"
    assert alt_cores == []


@pytest.mark.parametrize("noise", ["[DL版]", "[中国翻訳]"])
def test_noise_prefixed_copy_groups_with_canonical_copy(noise: str) -> None:
    """§7.1 / D3: ``[DL版] X`` and ``[Artist] X`` form one group (not two)."""
    items = [
        _fav(101, f"{noise} Secret Story"),
        _fav(102, "[Artist] Secret Story"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    assert groups[0]["key"] == "artist|secretstory"
    assert groups[0]["artist"] == "artist"
    assert {it["gid"] for it in groups[0]["items"]} == {101, 102}


def test_hangul_title_keeps_a_usable_core() -> None:
    """§7.2: Hangul is preserved, so Korean galleries stay in dedup."""
    assert normalize_title("사랑해") == "사랑해"
    artist, core, _ = extract_duplicate_artist_and_core("[Artist] 사랑해")
    assert artist == "artist"
    assert core == "사랑해"
    # 3 Hangul characters count 2 each, reaching DUP_CORE_MIN_EFFECTIVE_LEN.
    assert _core_effective_length(core) == 6

    items = [
        _fav(201, "[Artist] 사랑해"),
        _fav(202, "[Artist] 사랑해 [DL版]"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    assert groups[0]["key"] == "artist|사랑해"
    assert {it["gid"] for it in groups[0]["items"]} == {201, 202}


def test_fullwidth_title_folds_to_ascii_core() -> None:
    """§7.2: NFKC folding keeps full-width titles in dedup instead of blanking."""
    assert normalize_title("ＡＢＣ ＤＥＦ") == "abcdef"
    items = [
        _fav(211, "[Artist] ＡＢＣ ＤＥＦ"),
        _fav(212, "[Artist] ABC DEF"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert len(groups) == 1
    assert groups[0]["key"] == "artist|abcdef"
    assert {it["gid"] for it in groups[0]["items"]} == {211, 212}


def test_cross_language_copies_stay_unmerged() -> None:
    """§7.3: current behaviour is locked — English vs. Japanese copies do not group.

    ``parent_gid`` is persisted by the backend but not fed into clustering;
    changing that is a separate product decision.
    """
    items = [
        _fav(301, "[Artist] Secret Story"),
        _fav(302, "[Artist] 秘密の物語"),
    ]
    groups = find_duplicate_groups(items, gallery_titles={})
    assert groups == []


def test_gallery_appears_in_exactly_one_group() -> None:
    """§7.4: groups sharing a gallery are unioned into one group, never two."""
    galleries = [
        {
            "id": 1,
            "gid": 11,
            "title": "[Artist] Secret Story",
            "title_jpn": "[Artist] 秘密の物語",
        },
        {"id": 2, "gid": 12, "title": "[Artist] Secret Story", "title_jpn": None},
        {"id": 3, "gid": 13, "title": None, "title_jpn": "[Artist] 秘密の物語"},
    ]
    groups = find_gallery_duplicate_groups(galleries)

    assert len(groups) == 1
    assert groups[0]["artist"] == "artist"
    assert {it["gid"] for it in groups[0]["items"]} == {11, 12, 13}

    seen = [it["gid"] for group in groups for it in group["items"]]
    assert sorted(seen) == [11, 12, 13]
    assert len(seen) == len(set(seen))
