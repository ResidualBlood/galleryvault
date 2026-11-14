"""Durable task-run ledger used by the task state persistence layer.

``TaskManager`` keeps live state in memory for fast polling; this repository is
the append-only-ish history behind it (PLAN-backend-hardening T7.4/T7.5).  Each
call is a single statement so it is cheap enough to call from progress
updates, and every method assumes the caller owns the transaction (it flushes
but never commits), matching the other repositories.

Invariants enforced here and by the ``task_runs`` table:

* at most one ``running`` row per ``name`` (partial unique index);
* ``(name, run_id)`` is unique, so a new run never overwrites the previous one;
* ``payload`` is capped at 256 KiB; an oversized payload is replaced by a
  ``{"truncated": true, "original_bytes": N}`` marker instead of failing the
  write (the task itself must not fail because its detail is too large).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import TaskRun

RUNNING = "running"
FINISHED_STATUSES: tuple[str, ...] = ("success", "failed", "cancelled", "interrupted")
STATUSES: tuple[str, ...] = (RUNNING, *FINISHED_STATUSES)

MAX_NAME_LENGTH = 48
MAX_RUN_ID_LENGTH = 36
MAX_PAYLOAD_BYTES = 256 * 1024
SUPERSEDED_REASON = "superseded by new run"
INTERRUPTED_REASON = "interrupted by restart"


def _validate_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("task run name must be a non-empty string")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"task run name is longer than {MAX_NAME_LENGTH} characters: {name!r}")
    return name


def _json_size(value: Any) -> int:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    return len(encoded.encode("utf-8"))


def truncate_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return ``payload`` as a dict, bounded to :data:`MAX_PAYLOAD_BYTES`.

    The marker keeps the fact that detail existed without storing 10 MB of
    ``corrupt_ids``.  ``original_bytes`` uses the same canonical JSON encoding
    as the size check, so the value is reproducible in tests.
    """
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise TypeError("task run payload must be a mapping")
    data = dict(payload)
    size = _json_size(data)
    if size <= MAX_PAYLOAD_BYTES:
        return data
    return {"truncated": True, "original_bytes": size}


def _now() -> datetime:
    return datetime.now(UTC)


class TaskRunRepository:
    """Persistence for :class:`TaskRun` rows (see module docstring)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start(
        self,
        name: str,
        *,
        run_id: str | None = None,
        stage: str | None = None,
        cancellable: bool = False,
        payload: Mapping[str, Any] | None = None,
    ) -> str:
        """Open a new run for ``name`` and return its ``run_id``.

        A leftover ``running`` row for the same name (previous process died
        before boot-time reconciliation) is marked ``interrupted`` first so the
        partial unique index can accept the new row.  Callers that need a
        guaranteed fresh scan of stale rows should still call
        :meth:`mark_interrupted` at startup.
        """
        name = _validate_name(name)
        run_id = str(run_id or uuid.uuid4())
        if len(run_id) > MAX_RUN_ID_LENGTH:
            raise ValueError(f"task run id is longer than {MAX_RUN_ID_LENGTH} characters")

        now = _now()
        await self.session.execute(
            update(TaskRun)
            .where(TaskRun.name == name, TaskRun.status == RUNNING)
            .values(
                status="interrupted",
                reason=SUPERSEDED_REASON,
                completed_at=now,
                heartbeat_at=now,
                updated_at=now,
            )
        )
        await self.session.execute(
            pg_insert(TaskRun).values(
                name=name,
                run_id=run_id,
                status=RUNNING,
                stage=stage,
                cancellable=bool(cancellable),
                done=0,
                total=0,
                payload=truncate_payload(payload),
            )
        )
        return run_id

    async def heartbeat(
        self,
        name: str,
        done: int = 0,
        total: int = 0,
        stage: str | None = None,
        payload: Mapping[str, Any] | None = None,
        *,
        run_id: str | None = None,
    ) -> bool:
        """Update the live progress of the running row; returns whether it matched.

        ``stage`` and ``payload`` are only written when provided, so a caller
        can report progress without clearing a stage it already set.
        """
        _validate_name(name)
        now = _now()
        values: dict[str, Any] = {
            "done": int(done),
            "total": int(total),
            "heartbeat_at": now,
            "updated_at": now,
        }
        if stage is not None:
            values["stage"] = stage
        if payload is not None:
            values["payload"] = truncate_payload(payload)

        stmt = update(TaskRun).where(TaskRun.name == name, TaskRun.status == RUNNING)
        if run_id is not None:
            stmt = stmt.where(TaskRun.run_id == run_id)
        result = await self.session.execute(stmt.values(**values))
        return int(result.rowcount or 0) > 0

    async def finish(
        self,
        name: str,
        status: str,
        reason: str = "",
        *,
        run_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        last_error: str | None = None,
        done: int | None = None,
        total: int | None = None,
    ) -> bool:
        """Close the running row with a terminal ``status``; returns matched."""
        _validate_name(name)
        if status not in FINISHED_STATUSES:
            raise ValueError(f"invalid terminal task status: {status!r}")

        now = _now()
        values: dict[str, Any] = {
            "status": status,
            "reason": reason or None,
            "completed_at": now,
            "heartbeat_at": now,
            "updated_at": now,
        }
        if payload is not None:
            values["payload"] = truncate_payload(payload)
        if last_error is not None:
            values["last_error"] = last_error
        elif status == "failed" and reason:
            values["last_error"] = str(reason)
        if done is not None:
            values["done"] = int(done)
        if total is not None:
            values["total"] = int(total)

        stmt = update(TaskRun).where(TaskRun.name == name, TaskRun.status == RUNNING)
        if run_id is not None:
            stmt = stmt.where(TaskRun.run_id == run_id)
        result = await self.session.execute(stmt.values(**values))
        return int(result.rowcount or 0) > 0

    async def latest(self, name: str) -> TaskRun | None:
        """Return the newest run for ``name`` (running or finished), if any."""
        _validate_name(name)
        stmt = (
            select(TaskRun)
            .where(TaskRun.name == name)
            .order_by(TaskRun.started_at.desc(), TaskRun.id.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def history(self, limit: int = 50, *, name: str | None = None) -> list[TaskRun]:
        """Return recent runs, newest first (optionally for one task name)."""
        limit = int(limit)
        if limit <= 0:
            return []
        stmt = select(TaskRun).order_by(
            func.coalesce(TaskRun.completed_at, TaskRun.started_at).desc(),
            TaskRun.id.desc(),
        )
        if name is not None:
            stmt = stmt.where(TaskRun.name == _validate_name(name))
        stmt = stmt.limit(limit)
        rows = await self.session.scalars(stmt)
        return list(rows.all())

    async def mark_interrupted(self, reason: str = INTERRUPTED_REASON) -> int:
        """Mark every leftover ``running`` row as ``interrupted``; returns count."""
        now = _now()
        result = await self.session.execute(
            update(TaskRun)
            .where(TaskRun.status == RUNNING)
            .values(
                status="interrupted",
                reason=reason,
                completed_at=now,
                heartbeat_at=now,
                updated_at=now,
            )
        )
        return int(result.rowcount or 0)

    async def prune(self, keep_per_name: int = 20) -> int:
        """Delete finished rows older than the newest ``keep_per_name`` per name.

        Running rows are never pruned: they are the live state T7.5 restores
        from.  Returns the number of deleted rows.
        """
        keep = int(keep_per_name)
        if keep < 1:
            raise ValueError("keep_per_name must be at least 1")

        ranked = (
            select(
                TaskRun.id,
                func.row_number()
                .over(
                    partition_by=TaskRun.name,
                    order_by=(
                        func.coalesce(TaskRun.completed_at, TaskRun.started_at).desc(),
                        TaskRun.id.desc(),
                    ),
                )
                .label("rn"),
            )
            .where(TaskRun.status != RUNNING)
            .subquery()
        )
        stmt = delete(TaskRun).where(
            TaskRun.id.in_(select(ranked.c.id).where(ranked.c.rn > keep))
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)
