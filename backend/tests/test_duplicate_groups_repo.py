"""T5.1: duplicate_group merge rules, tested as a pure DB-free planner.

``plan_sync`` is the single write path used by ``DuplicateGroupRepository.sync``;
keeping the merge rules pure lets these tests run on the host without Postgres.
"""

from datetime import UTC, datetime

import pytest


def _row(row_id, kind, group_key, status, member_gids, *, legacy_keys=None, present=True):
    return {
        "id": row_id,
        "kind": kind,
        "group_key": group_key,
        "status": status,
        "member_gids": member_gids,
        "legacy_keys": legacy_keys or [],
        "title": None,
        "artist": None,
        "payload": {},
        "present": present,
        "dismissed_at": datetime(2026, 1, 1, tzinfo=UTC) if status == "dismissed" else None,
    }


def _group(key, gids, legacy_keys=None):
    return {
        "key": key,
        "items": [{"gid": gid} for gid in gids],
        "legacy_keys": legacy_keys or [],
    }


def test_sync_keeps_dismissed_when_key_drifts():
    from galleryvault.db.repositories.duplicates import plan_sync

    existing = [
        _row(1, "favorites", "alice|old", "dismissed", [1, 2], legacy_keys=["alice|legacy"])
    ]
    # Case A: same gid set, new display key, shared legacy key.
    plan = plan_sync(
        "favorites",
        [_group("alice|new", [2, 1], legacy_keys=["alice|legacy"])],
        existing,
    )
    assert plan.deletes == []
    assert len(plan.upserts) == 1
    update = plan.upserts[0]
    assert update.row_id == 1
    assert update.group_key == "alice|new"
    assert update.status == "dismissed"
    assert update.present is True
    assert update.member_gids == [1, 2]
    assert update.dismissed_at == existing[0]["dismissed_at"]

    # Case B: no legacy overlap but the new members are a subset of the old row.
    plan = plan_sync("favorites", [_group("alice|drifted", [1])], existing)
    assert len(plan.upserts) == 1
    assert plan.upserts[0].row_id == 1
    assert plan.upserts[0].status == "dismissed"


def test_sync_keeps_dismissed_when_group_disappears_and_returns():
    from galleryvault.db.repositories.duplicates import plan_sync

    existing = [_row(1, "cross_gid", "a|b", "dismissed", [5, 6])]
    plan = plan_sync("cross_gid", [], existing)
    assert plan.deletes == []
    assert len(plan.upserts) == 1
    gone = plan.upserts[0]
    assert gone.row_id == 1
    assert gone.present is False
    assert gone.status == "dismissed"
    assert gone.group_key == "a|b"

    # A dismissed, absent row must stay dismissed when the same group returns.
    returning = [_row(1, "cross_gid", "a|b", "dismissed", [5, 6], present=False)]
    plan = plan_sync("cross_gid", [_group("a|b", [6, 5])], returning)
    assert plan.deletes == []
    assert len(plan.upserts) == 1
    back = plan.upserts[0]
    assert back.present is True
    assert back.status == "dismissed"

    # An open group that disappears is removed instead of lingering.
    plan = plan_sync("cross_gid", [], [_row(2, "cross_gid", "c|d", "open", [7, 8])])
    assert plan.deletes == [2]
    assert plan.upserts == []


def test_sync_reopens_when_new_member_joins():
    from galleryvault.db.repositories.duplicates import plan_sync

    existing = [_row(1, "favorites", "a|b", "dismissed", [1, 2])]
    plan = plan_sync("favorites", [_group("a|b", [1, 2, 3])], existing)
    assert len(plan.upserts) == 1
    reopened = plan.upserts[0]
    assert reopened.row_id == 1
    assert reopened.status == "open"
    assert reopened.dismissed_at is None
    assert reopened.member_gids == [1, 2, 3]


def test_kinds_are_isolated():
    from galleryvault.db.repositories.duplicates import plan_sync

    existing = [
        _row(1, "favorites", "a|b", "dismissed", [1, 2]),
        _row(2, "cross_gid", "a|b", "open", [3, 4]),
    ]
    # The favorites ignore must not dismiss the cross_gid group with the same key.
    plan = plan_sync("cross_gid", [_group("a|b", [3, 4])], existing)
    assert [u.row_id for u in plan.upserts] == [2]
    assert plan.upserts[0].status == "open"
    assert plan.deletes == []

    # Emptying cross_gid only removes cross_gid rows.
    plan = plan_sync("cross_gid", [], existing)
    assert plan.deletes == [2]
    assert plan.upserts == []


def test_sync_normalizes_same_gid_input():
    from galleryvault.db.repositories.duplicates import plan_sync

    plan = plan_sync(
        "same_gid",
        [{"gid": 42, "policy": "keep_last", "winner_path": "/lib/42", "copies": [{"path": "/lib/42"}]}],
        [],
    )
    assert len(plan.upserts) == 1
    inserted = plan.upserts[0]
    assert inserted.row_id is None
    assert inserted.group_key == "42"
    assert inserted.status == "open"
    assert inserted.member_gids == [42]
    assert inserted.payload == {
        "policy": "keep_last",
        "winner_path": "/lib/42",
        "copies": [{"path": "/lib/42"}],
    }


def test_sync_rejects_unknown_kind():
    from galleryvault.db.repositories.duplicates import plan_sync

    with pytest.raises(ValueError):
        plan_sync("other", [], [])
