"""Status helpers for the converged ``duplicate_groups`` table (T5.3).

The routers no longer remember duplicate state in process memory or in the
legacy ``favorite_duplicate_ignores`` table: every list/dismiss/restore goes
through :class:`~galleryvault.db.repositories.duplicates.DuplicateGroupRepository`
and carries the row's ``kind``.  These helpers keep the kind check and the
"ignore a group we have not scanned yet" upsert in one place so the cross-GID
and favorites routers cannot drift apart again.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..db.models import AppConfig, DuplicateGroup
from ..db.repositories.duplicates import DuplicateGroupRepository
from ..db.repositories.task_runs import TaskRunRepository

# ``ready`` for the cross-GID page now derives from the durable task ledger
# (T7.5) instead of the ``duplicates_scan_cross_gid`` AppConfig marker.
_KIND_TASK_NAMES = {"cross_gid": "duplicates-cross-gid"}


def _scan_marker_key(kind: str) -> str:
    return f"duplicates_scan_{kind}"


async def mark_kind_scanned(session: Any, kind: str) -> None:
    """Persist "this kind finished a scan", even when it found no group.

    Kept for the legacy ``app_config`` marker; ``kind_scanned`` answers from the
    ``task_runs`` ledger since T7.5, so the marker is only historical and can be
    dropped once an install has run a scan after upgrading.
    """
    key = _scan_marker_key(kind)
    now = datetime.now(UTC)
    row = await session.get(AppConfig, key)
    value = {"scanned_at": now.isoformat()}
    if row is None:
        session.add(AppConfig(key=key, value=value, updated_at=now))
    else:
        row.value = value
        row.updated_at = now
    await session.flush()


async def kind_scanned(session: Any, kind: str) -> bool:
    """Return whether this kind has completed at least one scan (from task_runs)."""
    task_name = _KIND_TASK_NAMES.get(kind)
    if task_name is None or not hasattr(session, "scalar"):
        # Non-ORM session doubles (router unit tests) cannot query the ledger;
        # fall back to the legacy marker.  A real session always has ``scalar``.
        return await session.get(AppConfig, _scan_marker_key(kind)) is not None
    row = await TaskRunRepository(session).latest(task_name)
    return bool(
        row is not None
        and getattr(row, "status", None) == "success"
        and getattr(row, "completed_at", None) is not None
    )


async def list_groups(
    session: Any,
    kind: str,
    *,
    status: str | None = None,
    present: bool | None = None,
) -> list[DuplicateGroup]:
    """Return the rows of one kind, optionally filtered by status/presence."""
    return await DuplicateGroupRepository(session).list(kind, status=status, present=present)


async def get_group(session: Any, kind: str, group_id: int) -> DuplicateGroup | None:
    """Return one row of ``kind``; a row of another kind is reported as missing."""
    row = await DuplicateGroupRepository(session).get(group_id)
    if row is None or row.kind != kind:
        return None
    return row


async def set_group_status(
    session: Any, kind: str, group_id: int, status: str
) -> DuplicateGroup | None:
    """Set the status of one row of ``kind`` (``None`` when it does not exist)."""
    repo = DuplicateGroupRepository(session)
    row = await repo.get(group_id)
    if row is None or row.kind != kind:
        return None
    return await repo.set_status(group_id, status)


async def set_status_by_key(
    session: Any,
    kind: str,
    group_key: str,
    status: str,
    *,
    title: str | None = None,
    member_gids: list[int] | None = None,
) -> bool:
    """Dismiss/restore the row of ``kind`` identified by its display key.

    Ignores are keyed by ``artist|core`` on the API, so the favorites router
    cannot use the row id.  A dismissed row that does not exist yet is created
    (``present=false``): the user may ignore a group before the next scan
    reaches it, and the legacy ignore flow allowed exactly that.
    """
    repo = DuplicateGroupRepository(session)
    for row in await repo.list(kind):
        if row.group_key == group_key:
            await repo.set_status(row.id, status)
            if title:
                row.title = title
            if member_gids:
                row.member_gids = sorted({int(gid) for gid in member_gids})
            await session.flush()
            return True
    if status != "dismissed":
        return False

    now = datetime.now(UTC)
    session.add(
        DuplicateGroup(
            kind=kind,
            group_key=group_key,
            status="dismissed",
            member_gids=sorted({int(gid) for gid in member_gids or []}),
            legacy_keys=[],
            title=title or None,
            artist=None,
            payload={},
            present=False,
            last_seen_at=None,
            dismissed_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()
    return True


async def delete_group_by_key(session: Any, kind: str, group_key: str) -> bool:
    """Delete the row of ``kind`` identified by its display key (if any)."""
    repo = DuplicateGroupRepository(session)
    for row in await repo.list(kind):
        if row.group_key == group_key:
            return await repo.delete(row.id)
    return False


async def remove_group_copies(
    session: Any, kind: str, group_key: str, deleted_paths: list[str]
) -> bool:
    """Drop copies that were deleted from disk from one group's payload.

    Deletes the row when no copy survives (used by the deletion service once a
    staged multi-copy delete has finished).  Returns ``True`` when a row was
    found and updated or deleted.
    """
    repo = DuplicateGroupRepository(session)
    deleted = {str(Path(str(path)).resolve()) for path in deleted_paths}
    for row in await repo.list(kind):
        if row.group_key != group_key:
            continue
        payload = dict(row.payload or {})
        remaining = [
            copy
            for copy in payload.get("copies") or []
            if str(Path(str(copy.get("path") or "")).resolve()) not in deleted
        ]
        if not remaining:
            await repo.delete(row.id)
            return True
        payload["copies"] = remaining
        winner = payload.get("winner_path")
        if winner and str(Path(str(winner)).resolve()) in deleted:
            payload["winner_path"] = str(remaining[0].get("path") or "")
        row.payload = payload
        row.updated_at = datetime.now(UTC)
        await session.flush()
        return True
    return False
