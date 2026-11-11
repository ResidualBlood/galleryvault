"""Series artist extraction alignment with gallery-dedup 0.2.0.

Covers the round-2 audit gaps: leading version/translation noise brackets must
not become the artist, the ``A - B`` split needs the same guard as gallery-dedup,
and Hangul titles get an effective-length based match key.
"""

from __future__ import annotations

import pytest

from galleryvault.services.series import (
    _core_effective_length,
    compute_match_key,
    compute_series_key,
    extract_artist_and_stripped_title,
)


@pytest.mark.parametrize(
    "title",
    [
        "[DL版] Long Series Title 01",
        "[English] Long Series Title 01",
        "[中国翻訳] Long Series Title 01",
        "【无修】Long Series Title 01",
        "［DL版］Long Series Title 01",
    ],
)
def test_leading_noise_bracket_is_not_artist(title: str) -> None:
    artist, _ = extract_artist_and_stripped_title(title)
    assert artist == ""
    # Same cluster core as the real artist version of the same work.
    assert compute_series_key(title, None) == compute_series_key(
        "[Artist] Long Series Title 01", None
    )
    assert compute_match_key(title, None) == "s::::longseriestitle"


def test_noise_bracket_after_artist_keeps_artist() -> None:
    artist, stripped = extract_artist_and_stripped_title(
        "[Circle (Artist)] [DL版] Long Series Title 01"
    )
    assert artist == "artist"
    assert stripped == "Long Series Title"


def test_dash_split_guard_matches_dedup() -> None:
    # Left side has spaces and is longer than 24 chars -> no split.
    long_left = "Artist Name Is Very Long Here - Long Series Title 01"
    artist, stripped = extract_artist_and_stripped_title(long_left)
    assert artist == ""
    assert stripped == "Artist Name Is Very Long Here - Long Series Title"
    assert compute_match_key(long_left, None) == (
        "s::::artistnameisverylongherelongseriestitle"
    )

    # Right side core too short -> no split.
    assert extract_artist_and_stripped_title("A - Bc")[0] == ""

    # Short left side still splits (locked by test_series.py as well).
    assert extract_artist_and_stripped_title("exodus626 - 落难山村的少女") == (
        "exodus626",
        "落难山村的少女",
    )


def test_hangul_core_counts_as_wide_and_gets_match_key() -> None:
    assert _core_effective_length("가나다라마") == 10
    assert compute_match_key("가나다라마", None) == "s::::가나다라마"
    # 5 Hangul chars = effective length 10 >= 6, so a key exists.
    assert compute_match_key("가나다라마", None) is not None
    # ASCII still counts 1: 5 chars stay below the threshold.
    assert compute_match_key("abcde", None) is None
