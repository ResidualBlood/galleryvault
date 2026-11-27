"""Regression tests for batch-1 misc fixes (P3-9..P3-12 in review/05)."""

from __future__ import annotations

from pathlib import Path

import pytest

from galleryvault import observability
from galleryvault.logging import RingBufferHandler, _read_tail_lines
from galleryvault.services import messages, tag_translation
from galleryvault.services.tag_translation import (
    _rebuild_zh_exact_index,
    merge_translation_data,
    search_zh_exact,
    translate_tag,
)


def _line(i: int, payload: str = "") -> str:
    return f"2026-09-02T12:00:00+08:00 INFO     hyd: line {i}{payload}\n"


# --------------------------------------------------------------------------- P3-9


def test_tail_read_returns_only_newest_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "gv.log"
    log_file.write_text("".join(_line(i, "x" * 120) for i in range(2000)), encoding="utf-8")

    lines = _read_tail_lines(log_file, 3)

    assert len(lines) == 3
    assert lines == [
        _line(1997, "x" * 120).rstrip("\n"),
        _line(1998, "x" * 120).rstrip("\n"),
        _line(1999, "x" * 120).rstrip("\n"),
    ]
    # The chunk boundary must not leak a truncated fragment as the first line.
    assert all(line.startswith("2026-09-02T12:00:00+08:00 INFO") for line in lines)


def test_hydration_reads_bounded_tail_across_rotations(tmp_path: Path) -> None:
    log_file = tmp_path / "gv.log"
    backup = tmp_path / "gv.log.1"
    backup.write_text("".join(_line(i) for i in range(3)), encoding="utf-8")
    log_file.write_text("".join(_line(100 + i) for i in range(4)), encoding="utf-8")

    handler = RingBufferHandler(capacity=50)
    handler.hydrate_from_file(log_file, max_lines=5, backup_count=3)
    logs = handler.get_logs(min_level="DEBUG", limit=10)

    assert len(logs) == 5
    # Newest first: 4 current-file lines then the newest backup line.
    assert logs[0]["message"] == "line 103"
    assert logs[3]["message"] == "line 100"
    assert logs[4]["message"] == "line 2"


def test_hydration_stops_at_max_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "gv.log"
    log_file.write_text("".join(_line(i) for i in range(500)), encoding="utf-8")

    handler = RingBufferHandler(capacity=50)
    handler.hydrate_from_file(log_file, max_lines=7, backup_count=3)
    logs = handler.get_logs(min_level="DEBUG", limit=10)

    assert len(logs) == 7
    assert logs[0]["message"] == "line 499"
    assert logs[-1]["message"] == "line 493"


# -------------------------------------------------------------------------- P3-10


def test_metric_label_values_are_escaped() -> None:
    raw = 'a"b\\c\nd'
    observability.inc_counter("gv_b1g_escaped_total", 1, {"detail": raw})

    rendered = observability.render_metrics()
    expected = 'gv_b1g_escaped_total{detail="a\\"b\\\\c\\nd"} 1'
    assert expected in rendered
    # The escaped newline must not split the exposition line.
    metric_lines = [
        line for line in rendered.split("\n") if line.startswith("gv_b1g_escaped_total")
    ]
    assert metric_lines == [expected]


def test_histogram_metric_label_values_are_escaped() -> None:
    observability.observe_histogram(
        "gv_b1g_hist_seconds", 0.01, {"handler": 'x"y\nz'}, buckets=(0.1,)
    )

    rendered = observability.render_metrics()
    assert 'gv_b1g_hist_seconds_bucket{handler="x\\"y\\nz",le="0.1"} 1' in rendered


@pytest.mark.asyncio
async def test_request_id_middleware_uses_escaped_label_helper() -> None:
    from starlette.requests import Request
    from starlette.responses import Response

    scope = {"type": "http", "method": "GET", "path": "/metrics", "headers": [], "state": {}}
    request = Request(scope)

    async def call_next(_request):
        return Response(status_code=204)

    response = await observability.request_id_middleware(request, call_next)

    assert response.status_code == 204
    assert response.headers["X-Request-ID"] == request.state.request_id
    assert 'gv_http_requests_total{code="204"}' in observability.render_metrics()


# -------------------------------------------------------------------------- P3-11


def test_bot_quota_unavailable_is_localised() -> None:
    zh = messages.bot_quota(lang="zh")
    en = messages.bot_quota(lang="en")

    assert "无法获取" in zh
    assert "暂无数据" in zh
    assert "Quota unavailable" not in zh
    assert "Quota unavailable" in en


# -------------------------------------------------------------------------- P3-12


@pytest.fixture()
def empty_translations(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tag_translation, "_TRANSLATIONS", {})
    monkeypatch.setattr(tag_translation, "_ZH_EXACT", {})
    monkeypatch.setattr(tag_translation, "_ZH_SEARCH_ENTRIES", [])
    _rebuild_zh_exact_index()
    return tag_translation


def test_dict_form_expands_namespace_aliases(empty_translations) -> None:
    merge_translation_data({"other": {"x": "翻译"}})

    assert empty_translations._TRANSLATIONS["misc"]["x"] == "翻译"
    assert translate_tag("misc", "x") == "翻译"
    hit = search_zh_exact("翻译")
    assert hit is not None
    assert hit[1:] == ("x", "翻译")


def test_dict_form_expands_cosplayer_alias(empty_translations) -> None:
    merge_translation_data({"cosplayer": {"cos": "Coser"}})

    assert translate_tag("cosplay", "cos") == "Coser"


def test_index_rebuild_swaps_instead_of_mutating(empty_translations) -> None:
    merge_translation_data({"artist": {"a": "甲"}})
    previous = empty_translations._ZH_EXACT
    assert previous["甲"] == ("artist", "a", "甲")

    merge_translation_data({"female": {"f": "乙"}})

    assert empty_translations._ZH_EXACT is not previous
    # The old mapping is left intact for concurrent readers instead of being cleared.
    assert previous["甲"] == ("artist", "a", "甲")
    assert set(empty_translations._ZH_EXACT) == {"甲", "乙"}
