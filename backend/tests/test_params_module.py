"""Shared parameter parsing helpers live in ``galleryvault.app.params``."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi import HTTPException

from galleryvault.app import params
from galleryvault.app.routers import favorites as favorites_router
from galleryvault.app.routers import galleries as galleries_router

_REEXPORTED = (
    "_IMAGE_QUALITY",
    "_parse_posted",
    "_tags_for_galleries",
    "_tag_count",
    "_dedupe_tags",
    "_parse_tag_filter",
    "_resolve_search_tokens",
)


def test_routers_reexport_params_objects() -> None:
    for name in _REEXPORTED:
        assert getattr(galleries_router, name) is getattr(params, name)
        assert getattr(favorites_router, name) is getattr(params, name)


def test_favorites_does_not_import_galleries() -> None:
    source = Path(favorites_router.__file__).read_text(encoding="utf-8")
    assert "from .galleries import" not in source


def test_parse_posted_date_only_bounds() -> None:
    assert params._parse_posted(None) is None
    assert params._parse_posted("   ") is None
    assert params._parse_posted("2024-05-17") == datetime(2024, 5, 17, tzinfo=UTC)
    assert params._parse_posted("2024-05-17", upper=True) == datetime(2024, 5, 18, tzinfo=UTC)


def test_parse_posted_rejects_invalid() -> None:
    with pytest.raises(HTTPException) as excinfo:
        params._parse_posted("not-a-date")
    assert excinfo.value.status_code == 422


def test_parse_tag_filter_splits_include_and_exclude() -> None:
    inc, exc = params._parse_tag_filter("female:maid, big_breasts, -male:giant")
    assert inc == [("female", "maid"), (None, "big_breasts")]
    assert exc == [("male", "giant")]


def test_parse_tag_filter_rejects_invalid() -> None:
    with pytest.raises(HTTPException) as excinfo:
        params._parse_tag_filter("x" * 201)
    assert excinfo.value.status_code == 422


def test_dedupe_tags_and_tag_count() -> None:
    tags = [("female", "maid"), ("female", "maid"), (None, "solo")]
    assert params._dedupe_tags(tags) == [("female", "maid"), (None, "solo")]
    assert params._tag_count({1: tags}, 1) == 3
    assert params._tag_count({}, 1) == 0

    class _WithCounts(dict):
        counts: ClassVar[dict[int, int]] = {1: 7}

    assert params._tag_count(_WithCounts(), 1) == 7


def test_image_quality_values() -> None:
    assert params._IMAGE_QUALITY == frozenset({"original", "resample"})


async def test_resolve_search_tokens_splits_tags_and_keywords() -> None:
    inc, exc, keywords, changed = await params._resolve_search_tokens(
        "female:maid -male:giant plain"
    )
    assert inc == [("female", "maid")]
    assert exc == [("male", "giant")]
    assert keywords == "plain"
    assert changed is True


async def test_resolve_search_tokens_without_explicit_tags() -> None:
    assert await params._resolve_search_tokens("") == ([], [], "", False)
    inc, exc, keywords, changed = await params._resolve_search_tokens("plain words")
    assert (inc, exc, keywords, changed) == ([], [], "plain words", False)


class _Repo:
    def __init__(self) -> None:
        self.calls: list[list[int] | tuple[list[int], int]] = []

    async def tags_for_galleries(self, gallery_ids, limit=None):
        self.calls.append(gallery_ids if limit is None else (gallery_ids, limit))
        return {gallery_ids[0]: [("female", "maid")]} if gallery_ids else {}


async def test_tags_for_galleries_respects_limit_only_when_set() -> None:
    repo = _Repo()
    await params._tags_for_galleries(repo, [1], None)
    await params._tags_for_galleries(repo, [2], 5)
    assert repo.calls == [[1], ([2], 5)]
