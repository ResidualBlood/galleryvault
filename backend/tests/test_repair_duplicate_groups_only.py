"""T10.1d: the repair script only maintains ``duplicate_groups``.

The script used to dual-write the retired ``duplicate_records`` table (its
"until T5.3" comment outlived the migration). These tests pin that a rename
rewrites the converged group payloads, that no legacy table is scanned, and
that the CLI summary keeps the legacy ``duplicate_records_updated`` key name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

import pytest

from galleryvault.db.models import DuplicateGroup
from galleryvault.db.repositories.base import path_hash
from galleryvault.scripts.repair_cold_archives import (
    repair_cold_archives,
    update_duplicate_records_for_rename,
)


class _ScalarRows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _ScalarRows:
        return self

    def all(self) -> list[Any]:
        return self._rows


class _GroupSession:
    """Minimal async session answering the same-gid duplicate group scan."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.queries: list[str] = []

    async def scalars(self, query: Any) -> _ScalarRows:
        self.queries.append(str(query))
        return _ScalarRows(self.rows)


class _BoomSession:
    async def scalars(self, _query: Any) -> _ScalarRows:  # pragma: no cover - guard
        raise AssertionError("preloaded rows must not trigger a table scan")


def _group(gid: int, copies: list[dict[str, Any]], winner: str | None) -> DuplicateGroup:
    return DuplicateGroup(
        kind="same_gid",
        group_key=f"gid:{gid}",
        payload={"copies": copies, "winner_path": winner},
    )


@pytest.mark.asyncio
async def test_rename_rewrites_matching_group_payload() -> None:
    old_path = "/cold/a/100-old.cbz"
    new_path = "/cold/a/100-new.cbz"
    other_path = "/cold/a/100-other.cbz"
    matched = _group(
        100,
        [
            {"path": old_path, "key": path_hash(Path(old_path))},
            {"path": other_path, "key": "other-key"},
        ],
        old_path,
    )
    untouched = _group(200, [{"path": "/cold/b/200.cbz", "key": "b-key"}], "/cold/b/200.cbz")
    untouched_payload = untouched.payload
    session = _GroupSession([matched, untouched])

    changed = await update_duplicate_records_for_rename(session, old_path, new_path)

    assert changed == 1
    assert matched.payload["winner_path"] == new_path
    assert matched.payload["copies"][0] == {
        "path": new_path,
        "key": path_hash(Path(new_path)),
    }
    # A copy that was not at ``old_path`` keeps its own path/key.
    assert matched.payload["copies"][1] == {"path": other_path, "key": "other-key"}
    assert untouched.payload is untouched_payload
    assert session.queries, "the same-gid groups must be scanned once"
    assert "duplicate_groups" in session.queries[0]
    assert "duplicate_records" not in session.queries[0]


@pytest.mark.asyncio
async def test_rename_without_match_keeps_payload_untouched() -> None:
    group = _group(300, [{"path": "/cold/c/300.cbz", "key": "c-key"}], "/cold/c/300.cbz")
    payload_before = group.payload

    changed = await update_duplicate_records_for_rename(
        _GroupSession([group]), "/cold/c/999.cbz", "/cold/c/1000.cbz"
    )

    assert changed == 0
    assert group.payload is payload_before


@pytest.mark.asyncio
async def test_preloaded_rows_skip_the_table_scan() -> None:
    old_path = "/cold/d/400-old.cbz"
    new_path = "/cold/d/400-new.cbz"
    rows = [_group(400, [{"path": old_path, "key": path_hash(Path(old_path))}], old_path)]

    changed = await update_duplicate_records_for_rename(_BoomSession(), old_path, new_path, rows)

    assert changed == 1
    assert rows[0].payload["winner_path"] == new_path


@pytest.mark.asyncio
async def test_session_without_scalars_is_a_noop() -> None:
    changed = await update_duplicate_records_for_rename(
        object(), "/cold/e/500-old.cbz", "/cold/e/500-new.cbz"
    )

    assert changed == 0


class _EmptySession:
    """Session over an empty galleries table (no repairs needed)."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def execute(self, _query: Any) -> _ScalarRows:
        return _ScalarRows([])

    def add(self, _instance: Any) -> None:  # pragma: no cover - unused
        raise AssertionError("empty repair run must not add rows")

    async def commit(self) -> None:  # pragma: no cover - unused
        raise AssertionError("empty repair run must not commit")


@pytest.mark.asyncio
async def test_summary_keeps_legacy_duplicate_key() -> None:
    summary = await repair_cold_archives(lambda: _EmptySession(), execute=True)

    assert summary["duplicate_records_updated"] == 0
    assert "duplicate_records" not in summary
