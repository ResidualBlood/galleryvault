"""Persistence for duplicate groups detected by the three duplicate scanners.

A single table replaces the three former sources of truth (``duplicate_records``,
the in-memory cross-gid snapshot and ``favorite_duplicate_ignores``).  Every
scan funnels through :meth:`DuplicateGroupRepository.sync`, which is the only
writer: it reconciles the scan result against the stored rows so a dismissed
group survives key drift and temporarily-disappearing groups.

``plan_sync`` keeps the merge rules pure so they can be tested without a
database.  The rules (Batch 5 of PLAN-backend-hardening):

* rows are matched by ``(kind, group_key)``;
* an unmatched group inherits a dismissed row of the same kind when their
  ``legacy_keys`` intersect or the new members are a subset of the stored ones
  (the key drifts when upstream versions/merges change the display key);
* dismissed rows that are missing from the scan are kept with
  ``present=false``; open rows that are missing are deleted;
* a new member joining a dismissed group reopens it;
* the three kinds never share state, even when their ``group_key``s collide.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DuplicateGroup

KINDS: tuple[str, ...] = ("same_gid", "cross_gid", "favorites")
STATUSES: tuple[str, ...] = ("open", "dismissed")

_SAME_GID_FIELDS = ("policy", "winner_path", "copies")


@dataclass
class SyncUpsert:
    """One row to insert or update, produced by :func:`plan_sync`."""

    group_key: str
    status: str
    member_gids: list[int]
    legacy_keys: list[str]
    title: str | None
    artist: str | None
    payload: dict[str, Any]
    present: bool
    dismissed_at: datetime | None
    row_id: int | None = None


@dataclass
class SyncPlan:
    """Result of reconciling a scan with the stored rows of one kind."""

    upserts: list[SyncUpsert] = field(default_factory=list)
    deletes: list[int] = field(default_factory=list)


def _value(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _int_gids(values: Iterable[Any] | None) -> list[int]:
    gids: set[int] = set()
    for value in values or []:
        if value is None or isinstance(value, bool):
            continue
        try:
            gids.add(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(gids)


def _str_keys(values: Iterable[Any] | None) -> list[str]:
    return sorted({str(value) for value in values or [] if value})


def _validate_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown duplicate kind: {kind!r}")


def normalize_group(kind: str, group: Mapping[str, Any]) -> dict[str, Any]:
    """Coerce a scanner result into the canonical stored shape."""
    _validate_kind(kind)

    items = list(group.get("items") or [])
    member_gids = group.get("member_gids")
    if member_gids is None:
        member_gids = [
            item.get("gid")
            for item in items
            if isinstance(item, Mapping) and item.get("gid") is not None
        ]
    member_gids = _int_gids(member_gids)
    if not member_gids and kind == "same_gid" and group.get("gid") is not None:
        member_gids = _int_gids([group.get("gid")])

    group_key = group.get("group_key") or group.get("key")
    if not group_key and kind == "same_gid" and member_gids:
        group_key = str(member_gids[0])
    if not group_key:
        raise ValueError("duplicate group has neither group_key nor key")

    payload = group.get("payload")
    if payload is None:
        if kind == "same_gid":
            payload = {name: group.get(name) for name in _SAME_GID_FIELDS}
        else:
            payload = {"items": items}
    if not isinstance(payload, Mapping):
        raise TypeError("duplicate group payload must be a mapping")

    return {
        "group_key": str(group_key),
        "member_gids": member_gids,
        "legacy_keys": _str_keys(group.get("legacy_keys")),
        "title": group.get("title"),
        "artist": group.get("artist"),
        "payload": dict(payload),
    }


def plan_sync(kind: str, groups: Iterable[Mapping[str, Any]], existing: Iterable[Any]) -> SyncPlan:
    """Pure reconciliation of one scan result against stored rows.

    ``existing`` may contain rows of other kinds (they are ignored) and accepts
    ``DuplicateGroup`` instances or plain mappings.
    """
    _validate_kind(kind)

    rows = [row for row in existing if _value(row, "kind") == kind]
    consumed: set[int] = set()

    # Deduplicate the scan by key; the last occurrence wins.
    normalized: dict[str, dict[str, Any]] = {}
    for raw in groups:
        group = normalize_group(kind, raw)
        normalized[group["group_key"]] = group

    matched: dict[str, int] = {}
    by_key: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_key.setdefault(str(_value(row, "group_key")), []).append(index)

    for key in normalized:
        candidates = [index for index in by_key.get(key, []) if index not in consumed]
        if candidates:
            matched[key] = candidates[0]
            consumed.add(candidates[0])

    # Key drift: a dismissed row whose legacy keys or member set still identify
    # the same group keeps its dismissed state under the new key.
    for key, group in normalized.items():
        if key in matched:
            continue
        gids = set(group["member_gids"])
        keys = set(group["legacy_keys"])
        for index, row in enumerate(rows):
            if index in consumed or _value(row, "status") != "dismissed":
                continue
            legacy = set(_str_keys(_value(row, "legacy_keys")))
            stored_gids = set(_int_gids(_value(row, "member_gids")))
            if (keys & legacy) or (gids and gids <= stored_gids):
                matched[key] = index
                consumed.add(index)
                break

    plan = SyncPlan()
    for key, group in normalized.items():
        index = matched.get(key)
        if index is None:
            plan.upserts.append(
                SyncUpsert(
                    group_key=key,
                    status="open",
                    member_gids=list(group["member_gids"]),
                    legacy_keys=list(group["legacy_keys"]),
                    title=group["title"],
                    artist=group["artist"],
                    payload=group["payload"],
                    present=True,
                    dismissed_at=None,
                )
            )
            continue

        row = rows[index]
        stored_status = _value(row, "status")
        stored_gids = set(_int_gids(_value(row, "member_gids")))
        new_members = set(group["member_gids"]) - stored_gids
        status = stored_status if stored_status == "dismissed" and not new_members else "open"
        dismissed_at = _value(row, "dismissed_at") if status == "dismissed" else None
        plan.upserts.append(
            SyncUpsert(
                group_key=key,
                status=status,
                member_gids=list(group["member_gids"]),
                legacy_keys=sorted(
                    set(group["legacy_keys"]) | set(_str_keys(_value(row, "legacy_keys")))
                ),
                title=group["title"] or _value(row, "title"),
                artist=group["artist"] or _value(row, "artist"),
                payload=group["payload"],
                present=True,
                dismissed_at=dismissed_at,
                row_id=_value(row, "id"),
            )
        )

    for index, row in enumerate(rows):
        if index in consumed:
            continue
        row_id = _value(row, "id")
        if _value(row, "status") == "dismissed":
            plan.upserts.append(
                SyncUpsert(
                    group_key=str(_value(row, "group_key")),
                    status="dismissed",
                    member_gids=_int_gids(_value(row, "member_gids")),
                    legacy_keys=_str_keys(_value(row, "legacy_keys")),
                    title=_value(row, "title"),
                    artist=_value(row, "artist"),
                    payload=dict(_value(row, "payload") or {}),
                    present=False,
                    dismissed_at=_value(row, "dismissed_at"),
                    row_id=row_id,
                )
            )
        elif row_id is not None:
            plan.deletes.append(row_id)

    return plan


class DuplicateGroupRepository:
    """Read/write access to the converged ``duplicate_groups`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def sync(self, kind: str, groups: Iterable[Mapping[str, Any]]) -> list[DuplicateGroup]:
        """Reconcile one kind with a scan result and persist the differences.

        The caller owns the transaction; ``sync`` flushes but never commits.
        Returns the rows that are present in this scan, in scan order.
        """
        _validate_kind(kind)
        rows = list(
            (
                await self.session.scalars(
                    select(DuplicateGroup).where(DuplicateGroup.kind == kind)
                )
            ).all()
        )
        plan = plan_sync(kind, groups, rows)
        by_id = {row.id: row for row in rows}
        now = datetime.now(UTC)

        saved: list[DuplicateGroup] = []
        for upsert in plan.upserts:
            row = by_id.get(upsert.row_id) if upsert.row_id is not None else None
            if row is None:
                row = DuplicateGroup(kind=kind, group_key=upsert.group_key)
                self.session.add(row)
            row.group_key = upsert.group_key
            row.status = upsert.status
            row.member_gids = upsert.member_gids
            row.legacy_keys = upsert.legacy_keys
            row.title = upsert.title
            row.artist = upsert.artist
            row.payload = upsert.payload
            row.present = upsert.present
            row.dismissed_at = upsert.dismissed_at
            if upsert.present:
                row.last_seen_at = now
            row.updated_at = now
            saved.append(row)

        for row_id in plan.deletes:
            row = by_id.get(row_id)
            if row is not None:
                await self.session.delete(row)

        await self.session.flush()
        return saved

    async def get(self, group_id: int) -> DuplicateGroup | None:
        return await self.session.get(DuplicateGroup, group_id)

    async def list(
        self,
        kind: str | None = None,
        status: str | None = None,
        present: bool | None = None,
    ) -> list[DuplicateGroup]:
        stmt = select(DuplicateGroup)
        if kind is not None:
            _validate_kind(kind)
            stmt = stmt.where(DuplicateGroup.kind == kind)
        if status is not None:
            if status not in STATUSES:
                raise ValueError(f"unknown duplicate status: {status!r}")
            stmt = stmt.where(DuplicateGroup.status == status)
        if present is not None:
            stmt = stmt.where(DuplicateGroup.present.is_(present))
        stmt = stmt.order_by(DuplicateGroup.id)
        return list((await self.session.scalars(stmt)).all())

    async def set_status(self, group_id: int, status: str) -> DuplicateGroup | None:
        if status not in STATUSES:
            raise ValueError(f"unknown duplicate status: {status!r}")
        row = await self.session.get(DuplicateGroup, group_id)
        if row is None:
            return None
        row.status = status
        row.dismissed_at = datetime.now(UTC) if status == "dismissed" else None
        await self.session.flush()
        return row

    async def delete(self, group_id: int) -> bool:
        row = await self.session.get(DuplicateGroup, group_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True
