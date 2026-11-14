"""Unified background task state machine and registry."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from ..db.repositories.task_runs import (
    FINISHED_STATUSES,
    RUNNING,
    TaskRunRepository,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Cancelled-task markers are consumed when the task reaches a terminal state,
# but a pending task that is cancelled and then deleted/never claimed would
# otherwise leave its marker behind forever (report 01 P3-8). Keep the most
# recent markers only; older ones belong to tasks that are long gone.
_MAX_CANCELLED_MARKERS = 512
_HISTORY_LIMIT = 200

# Persisting every progress tick would write once per gallery/page; T7.5 requires
# at most one heartbeat per second unless the reported status actually changed.
_PROGRESS_PERSIST_INTERVAL = 1.0

# Indirection so tests can advance the throttle clock without sleeping.
_monotonic = time.monotonic

_STATUS_ALIASES = {
    "completed": "success",
    "done": "success",
    "ok": "success",
    "error": "failed",
    "canceled": "cancelled",
}


def _normalize_finished_status(value: Any) -> str:
    """Map the loose status strings used by ``record_task`` callers.

    ``TaskDispatcher`` reports ``"completed"`` while task workers use
    ``"success"``/``"failed"``; the ledger CHECK only accepts the canonical set.
    """
    status = str(value or "").strip().lower()
    status = _STATUS_ALIASES.get(status, status)
    if status in FINISHED_STATUSES:
        return status
    if "fail" in status or "error" in status:
        return "failed"
    return "success"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class TaskProgress:
    task: str
    running: bool = False
    started_at: str | None = None
    completed_at: str | None = None
    stage: str | None = None
    done: int = 0
    total: int | None = None
    cancellable: bool = True
    last_error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update(self.meta)
        return d


class TaskTracker:
    """Wrapper around task state dictionary for structured progress reporting."""

    def __init__(
        self,
        task_name: str,
        state: dict[str, Any],
        manager: TaskManager | None = None,
    ):
        self.task_name = task_name
        self.state = state
        self.manager = manager

    def update(self, **kwargs: Any) -> None:
        self.state.update(kwargs)
        if self.manager is not None:
            self.manager._maybe_persist_progress(self.task_name, self.state)

    def __getitem__(self, key: str) -> Any:
        return self.state[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def setdefault(self, key: str, default: Any = None) -> Any:
        return self.state.setdefault(key, default)


class TaskManager:
    """Manages live task states, cancellation flags, and history persistence."""

    def __init__(self, session_factory: Callable[[], AsyncSession] | None = None):
        self.session_factory = session_factory
        self.task_history: list[dict[str, Any]] = []
        self._cancelled_tasks: set[str | int] = set()
        self._cancelled_order: deque[str | int] = deque()

        # In-memory backward-compatible state dictionaries
        self.scan_state: dict[str, Any] = {
            "running": False,
            "last": None,
            "started_at": None,
            "completed_at": None,
        }
        self.tag_sync_state: dict[str, Any] = {
            "running": False,
            "total": 0,
            "queued": 0,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "retries": 0,
            "interval": None,
            "last_error": None,
            "started_at": None,
            "completed_at": None,
            "history_recorded": False,
            "category_refreshed": 0,
            "category_refresh_running": False,
        }
        self.thumb_state: dict[str, Any] = {
            "running": False,
            "queued": 0,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "total": 0,
            "last_error": None,
            "started_at": None,
            "completed_at": None,
            "history_recorded": False,
        }
        self.favorites_check_state: dict[str, Any] = {
            "running": False,
            "categories": {},
            "last_error": None,
            "started_at": None,
            "completed_at": None,
            "history_recorded": False,
            "skip_counts": {},
        }
        self.duplicates_state: dict[str, Any] = {
            "running": False,
            "stage": None,
            "done": 0,
            "total": 0,
            "last_error": None,
            "groups": [],
        }
        self.gallery_updates_state: dict[str, Any] = {
            "detecting": False,
            "last_detected_at": None,
            "found": 0,
            "last_error": None,
            "last_run": None,
        }
        self.metadata_sync_state: dict[str, Any] = {
            "running": False,
            "stage": None,
            "done": 0,
            "total": 0,
            "applied": 0,
            "last_error": None,
            "started_at": None,
            "completed_at": None,
        }
        self.translation_state: dict[str, Any] = {
            "running": False,
            "last": None,
            "last_error": None,
            "entries": 0,
            "started_at": None,
            "completed_at": None,
            "history_recorded": False,
        }
        self.archive_state: dict[str, Any] = {
            "running": False,
            "done": 0,
            "total": 0,
            "skipped": 0,
            "failed": 0,
            "last_error": None,
            "started_at": None,
            "completed_at": None,
        }
        self.unarchive_state: dict[str, Any] = {
            "running": False,
            "done": 0,
            "total": 0,
            "skipped": 0,
            "failed": 0,
            "last_error": None,
            "started_at": None,
            "completed_at": None,
        }
        self.integrity_state: dict[str, Any] = {
            "running": False,
            "started_at": None,
            "completed_at": None,
            "scanned": 0,
            "total": 0,
            "corrupt_ids": [],
            "last_error": None,
        }
        self.dynamic_states: dict[str, Any] = {}
        self._active_tasks: dict[str, int] = {}
        # Durable ledger wiring (T7.5). The run id of the active run per task
        # name, the throttle bookkeeping, and the fire-and-forget heartbeat
        # tasks that ``track_task`` drains before writing the terminal row.
        self._run_ids: dict[str, str] = {}
        self._last_persist: dict[str, tuple[float, int, int, str | None, tuple[Any, ...]]] = {}
        self._persist_jobs: set[asyncio.Task[Any]] = set()

    # Cancellation flags
    def request_cancel(self, task_key: str | int) -> None:
        if task_key not in self._cancelled_tasks:
            self._cancelled_order.append(task_key)
        self._cancelled_tasks.add(task_key)
        while len(self._cancelled_order) > _MAX_CANCELLED_MARKERS:
            self._cancelled_tasks.discard(self._cancelled_order.popleft())

    def clear_cancelled(self, task_key: str | int) -> None:
        self._cancelled_tasks.discard(task_key)
        try:
            self._cancelled_order.remove(task_key)
        except ValueError:
            pass

    def is_cancelled(self, task_key: str | int) -> bool:
        return task_key in self._cancelled_tasks

    def _resolve_task_state(self, task_name: str) -> dict[str, Any]:
        state_map = {
            "scan": self.scan_state,
            "tag-sync": self.tag_sync_state,
            "thumbs": self.thumb_state,
            "metadata": self.metadata_sync_state,
            "favcheck": self.favorites_check_state,
            "favorites-check": self.favorites_check_state,
            "translation": self.translation_state,
            "duplicates": self.duplicates_state,
            "gallery-updates": self.gallery_updates_state,
            "archive": self.archive_state,
            "unarchive": self.unarchive_state,
            "integrity": self.integrity_state,
        }
        if task_name in state_map:
            return state_map[task_name]
        return self.dynamic_states.setdefault(task_name, {})

    def _extract_progress(self, task_name: str, state: dict[str, Any]) -> tuple[int, int]:
        if task_name in ("favcheck", "favorites-check"):
            categories = state.get("categories")
            if isinstance(categories, dict):
                cat_rows = [c for c in categories.values() if isinstance(c, dict)]
                done = sum(int(c.get("done") or 0) for c in cat_rows)
                total = sum(int(c.get("total") or 0) for c in cat_rows)
                return done, total
        if task_name == "thumbs":
            succeeded = int(state.get("succeeded") or 0)
            failed = int(state.get("failed") or 0)
            done = int(state.get("processed") or (succeeded + failed))
            total = int(state.get("total") or 0)
            return done, total
        if task_name == "scan":
            return int(state.get("scanned") or state.get("persisted") or 0), int(state.get("total") or 0)
        if task_name == "tag-sync":
            return int(state.get("processed") or 0), int(state.get("total") or 0)
        if task_name == "translation":
            return int(state.get("entries") or 0), int(state.get("total") or 0)
        if task_name == "gallery-updates":
            return int(state.get("found") or 0), int(state.get("total") or 0)
        if task_name == "integrity":
            return int(state.get("scanned") or 0), int(state.get("total") or 0)
        done = int(
            state.get("done")
            or state.get("processed")
            or state.get("scanned")
            or state.get("entries")
            or state.get("found")
            or 0
        )
        total = int(state.get("total") or 0)
        return done, total

    _STATE_NAMES: ClassVar[dict[str, str]] = {
        "scan": "scan_state",
        "tag-sync": "tag_sync_state",
        "thumbs": "thumb_state",
        "metadata": "metadata_sync_state",
        "favorites-check": "favorites_check_state",
        "translation": "translation_state",
        "duplicates": "duplicates_state",
        "gallery-updates": "gallery_updates_state",
        "archive": "archive_state",
        "unarchive": "unarchive_state",
        "integrity": "integrity_state",
    }

    _PROGRESS_KEYS: ClassVar[dict[str, str]] = {
        "scan": "scanned",
        "tag-sync": "processed",
        "thumbs": "processed",
        "metadata": "done",
        "translation": "entries",
        "duplicates": "done",
        "gallery-updates": "found",
        "archive": "done",
        "unarchive": "done",
        "integrity": "scanned",
    }

    @staticmethod
    def _canonical_name(task_name: str) -> str:
        return "favorites-check" if task_name in ("favcheck", "favorites-check") else task_name

    @staticmethod
    def _state_signature(state: dict[str, Any]) -> tuple[Any, ...]:
        """Fields whose change must bypass the 1s heartbeat throttle."""
        return (
            state.get("stage"),
            state.get("last_error"),
            bool(state.get("running")),
            state.get("status"),
            bool(state.get("detecting")),
        )

    def _spawn_persist(self, coroutine: Any, operation: str) -> None:
        """Schedule a ledger write without letting it affect the task itself."""
        try:
            from ..app.dependencies import spawn_task

            task = spawn_task(coroutine, operation)
        except Exception as exc:  # noqa: BLE001
            close = getattr(coroutine, "close", None)
            if close is not None:
                close()
            logger.warning(
                "failed to schedule task run persistence",
                extra={"operation": operation, "error": type(exc).__name__},
            )
            return
        if task is None:
            return
        self._persist_jobs.add(task)
        task.add_done_callback(self._persist_jobs.discard)

    async def _drain_persist_jobs(self) -> None:
        """Wait for in-flight heartbeats so the terminal write is last."""
        while self._persist_jobs:
            pending = list(self._persist_jobs)
            self._persist_jobs.clear()
            await asyncio.gather(*pending, return_exceptions=True)

    def begin_task(self, task_name: str, *, cancellable: bool = False) -> dict[str, Any]:
        """Mark a dict-backed task as running (no ledger write yet).

        Routers and legacy workers used to mutate ``*_state`` directly; going
        through this method keeps the lifecycle fields consistent and lets
        :meth:`track_task` own the durable ``running`` row.
        """
        state = self._resolve_task_state(task_name)
        now = _utc_now_iso()
        if task_name == "gallery-updates":
            state["detecting"] = True
            state["last_run"] = now
        else:
            state["running"] = True
        state["started_at"] = now
        state["completed_at"] = None
        state["last_error"] = None
        state["history_recorded"] = False
        state["cancellable"] = cancellable
        return state

    def set_task_running(self, task_name: str, running: bool) -> None:
        """Flip only the ``running`` flag (e.g. seeding found no pending work)."""
        self._resolve_task_state(task_name)["running"] = bool(running)

    def mark_cancelling(self, task_name: str) -> None:
        """Expose the "cancel requested" UI state without touching the ledger."""
        state = self._resolve_task_state(task_name)
        state["status"] = "cancelling"
        state["running"] = False
        try:
            from ..app.state import app_state

            legacy = getattr(app_state, "scan_state", None)
            if isinstance(legacy, dict):
                legacy["status"] = "cancelling"
                legacy["running"] = False
        except Exception:  # noqa: BLE001, S110
            pass

    async def begin_persisted_task(
        self, task_name: str, *, cancellable: bool = True
    ) -> dict[str, Any]:
        """Start a dict-backed task that is not wrapped in :meth:`track_task`.

        ``thumbs`` is driven by the background job queue rather than a single
        coroutine, so the router opens the ledger row itself; the worker's final
        ``record_task`` call closes it.
        """
        state = self.begin_task(task_name, cancellable=cancellable)
        canonical = self._canonical_name(task_name)
        await self._persist_start(canonical, cancellable, state)
        return state

    async def _persist_start(
        self, task_name: str, cancellable: bool, state: dict[str, Any]
    ) -> str | None:
        session_cm = self.session_factory
        if session_cm is None:
            return None
        try:
            async with session_cm() as session, session.begin():
                run_id = await TaskRunRepository(session).start(
                    task_name,
                    stage=state.get("stage"),
                    cancellable=cancellable,
                    started_at=state.get("started_at"),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "failed to open task run; task continues without persistence",
                extra={"task": task_name, "error": type(exc).__name__, "detail": str(exc)[:200]},
            )
            return None
        self._run_ids[task_name] = run_id
        self._last_persist[task_name] = (
            _monotonic(),
            0,
            0,
            state.get("stage"),
            self._state_signature(state),
        )
        return run_id

    def _maybe_persist_progress(self, task_name: str, state: dict[str, Any]) -> None:
        canonical = self._canonical_name(task_name)
        run_id = self._run_ids.get(canonical)
        if not run_id:
            return
        done, total = self._extract_progress(task_name, state)
        stage = state.get("stage")
        signature = self._state_signature(state)
        now = _monotonic()
        last = self._last_persist.get(canonical)
        if (
            last is not None
            and now - last[0] < _PROGRESS_PERSIST_INTERVAL
            and signature == last[4]
        ):
            return
        self._last_persist[canonical] = (now, done, total, stage, signature)
        self._spawn_persist(
            self._heartbeat_run(canonical, run_id, done, total, stage),
            f"task run heartbeat {canonical}",
        )

    async def _heartbeat_run(
        self,
        task_name: str,
        run_id: str,
        done: int,
        total: int,
        stage: str | None,
    ) -> None:
        session_cm = self.session_factory
        if session_cm is None:
            return
        try:
            async with session_cm() as session, session.begin():
                await TaskRunRepository(session).heartbeat(
                    task_name,
                    done=done,
                    total=total,
                    stage=stage,
                    run_id=run_id,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "failed to persist task progress",
                extra={"task": task_name, "error": type(exc).__name__},
            )

    async def _persist_finish(
        self,
        task_name: str,
        status: str,
        reason: str,
        done: int,
        total: int,
        last_error: str | None,
        completed_at: str | None = None,
    ) -> None:
        run_id = self._run_ids.pop(task_name, None)
        self._last_persist.pop(task_name, None)
        await self._drain_persist_jobs()
        if run_id is None:
            return
        session_cm = self.session_factory
        if session_cm is None:
            return
        try:
            async with session_cm() as session, session.begin():
                await TaskRunRepository(session).finish(
                    task_name,
                    _normalize_finished_status(status),
                    reason=reason,
                    run_id=run_id,
                    last_error=last_error,
                    done=done,
                    total=total,
                    completed_at=completed_at,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "failed to close task run",
                extra={"task": task_name, "error": type(exc).__name__},
            )

    async def _persist_record(self, record: dict[str, Any]) -> None:
        """Persist one ``record_task`` entry into ``task_runs``."""
        session_cm = self.session_factory
        if session_cm is None:
            return
        task_name = str(record.get("task") or "")
        if not task_name:
            return
        status = _normalize_finished_status(record.get("status"))
        reason = str(record.get("reason") or "")
        done = int(record.get("done") or 0)
        total = int(record.get("total") or 0)
        started_at = _parse_datetime(record.get("started_at"))
        completed_at = _parse_datetime(record.get("completed_at"))
        last_error = reason if status == "failed" and reason else None
        try:
            async with session_cm() as session, session.begin():
                repository = TaskRunRepository(session)
                matched = await repository.finish(
                    task_name,
                    status,
                    reason=reason,
                    run_id=self._run_ids.get(task_name),
                    done=done,
                    total=total,
                    last_error=last_error,
                    completed_at=completed_at,
                )
                if not matched:
                    await repository.record(
                        task_name,
                        status,
                        started_at=started_at,
                        completed_at=completed_at,
                        reason=reason,
                        done=done,
                        total=total,
                        last_error=last_error,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "failed to persist task record",
                extra={"task": task_name, "error": type(exc).__name__},
            )

    async def history_records(self, limit: int = _HISTORY_LIMIT) -> list[dict[str, Any]]:
        """Return the finished task log, reading ``task_runs`` (T7.5).

        The process-local ``task_history`` is merged in to cover the short
        window before a fire-and-forget write lands; after a restart the ledger
        is the only source.  When the ledger is unreachable the in-memory list
        is returned (a warning was already logged by the writer).
        """
        local = list(self.task_history)
        session_cm = self.session_factory
        if session_cm is None:
            return local[:limit]
        try:
            async with session_cm() as session:
                rows = await TaskRunRepository(session).history(limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "failed to read task run history; using in-memory records",
                extra={"error": type(exc).__name__},
            )
            return local[:limit]
        records = [self._run_to_record(row) for row in rows if row.status != RUNNING]
        return self._merge_history(records, local)[:limit]

    @staticmethod
    def _run_to_record(row: Any) -> dict[str, Any]:
        return {
            "task": row.name,
            "started_at": _isoformat(row.started_at),
            "completed_at": _isoformat(row.completed_at),
            "status": row.status,
            "reason": row.reason or "",
            "done": int(row.done or 0),
            "total": int(row.total or 0),
        }

    async def restore_state(self) -> None:
        """Reconcile leftover running rows and rehydrate the live dicts.

        Called once at startup, before any worker runs: every ``running`` row is
        marked ``interrupted`` (a previous process died mid-task), then the
        newest row per task name is copied back into the corresponding
        ``*_state`` dict with ``running=False``.
        """
        session_cm = self.session_factory
        if session_cm is None:
            return
        try:
            async with session_cm() as session, session.begin():
                repository = TaskRunRepository(session)
                interrupted = await repository.mark_interrupted()
                rows = {
                    name: await repository.latest(name) for name in self._STATE_NAMES
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "failed to restore task state from task_runs",
                extra={"error": type(exc).__name__, "detail": str(exc)[:200]},
            )
            return
        if interrupted:
            logger.info("marked interrupted task runs at startup", extra={"count": interrupted})
        for name, row in rows.items():
            self._apply_restored_row(name, row)

    def _apply_restored_row(self, task_name: str, row: Any) -> None:
        state = self._resolve_task_state(task_name)
        if task_name == "gallery-updates":
            state["detecting"] = False
        else:
            state["running"] = False
        if row is None:
            return
        started_at = _isoformat(getattr(row, "started_at", None))
        completed_at = _isoformat(getattr(row, "completed_at", None))
        if "started_at" in state:
            state["started_at"] = started_at
        if "completed_at" in state:
            state["completed_at"] = completed_at
        if "last_error" in state:
            state["last_error"] = getattr(row, "last_error", None)
        if task_name == "gallery-updates":
            state["last_run"] = completed_at or started_at
        progress_key = self._PROGRESS_KEYS.get(task_name)
        if progress_key is not None:
            state[progress_key] = int(getattr(row, "done", 0) or 0)
        if "total" in state:
            state["total"] = int(getattr(row, "total", 0) or 0)

    @asynccontextmanager
    async def track_task(
        self,
        task_name: str,
        cancellable: bool = False,
        record_if_empty: bool = True,
    ):
        """Asynchronous context manager tracking task lifecycle, error logging, and history persistence."""
        state = self._resolve_task_state(task_name)
        active_count = self._active_tasks.get(task_name, 0) + 1
        self._active_tasks[task_name] = active_count

        now = _utc_now_iso()
        if active_count == 1:
            if cancellable:
                self.clear_cancelled(task_name)
            if task_name == "gallery-updates":
                state["detecting"] = True
                state["last_run"] = now
            else:
                state["running"] = True
            state["started_at"] = now
            state["completed_at"] = None
            state["last_error"] = None
            state["history_recorded"] = False
            state["cancellable"] = cancellable

        tracker = TaskTracker(task_name, state, self)
        status = "success"
        reason = ""
        canonical_name = self._canonical_name(task_name)
        if active_count == 1:
            await self._persist_start(canonical_name, cancellable, state)
        try:
            yield tracker
        except asyncio.CancelledError:
            status = "cancelled"
            reason = "cancelled"
            state["last_error"] = "cancelled"
            raise
        except Exception as exc:
            status = "failed"
            reason = state.get("last_error") or f"{type(exc).__name__}: {exc}"
            state["last_error"] = str(reason)
            raise
        finally:
            active_count = max(0, self._active_tasks.get(task_name, 1) - 1)
            self._active_tasks[task_name] = active_count

            if active_count == 0:
                completed_at = _utc_now_iso()
                state["completed_at"] = completed_at
                if task_name == "gallery-updates":
                    state["detecting"] = False
                    state["last_run"] = completed_at
                else:
                    state["running"] = False

                if self.is_cancelled(task_name):
                    status = "cancelled"
                    reason = "cancelled"
                    self.clear_cancelled(task_name)
                elif state.get("last_error"):
                    err = str(state.get("last_error"))
                    if err == "cancelled":
                        status = "cancelled"
                        reason = "cancelled"
                    elif status == "success":
                        status = "failed"
                        reason = err
                elif task_name in ("favcheck", "favorites-check"):
                    categories = state.get("categories")
                    if isinstance(categories, dict):
                        cat_rows = [c for c in categories.values() if isinstance(c, dict)]
                        if any(c.get("error") for c in cat_rows):
                            status = "failed"
                            reason = next(
                                (str(c.get("error")) for c in cat_rows if c.get("error")),
                                "failed",
                            )

                if state.get("reason"):
                    reason = str(state["reason"])

                done, total = self._extract_progress(task_name, state)

                if not state.get("history_recorded"):
                    state["history_recorded"] = True
                    skip_record = (
                        not record_if_empty
                        and status == "success"
                        and done == 0
                        and total == 0
                    )
                    if not skip_record:
                        self.record_task(
                            task=canonical_name,
                            started_at=state.get("started_at"),
                            completed_at=completed_at,
                            status=status,
                            reason=str(reason or ""),
                            done=done,
                            total=total,
                            persist=False,
                        )
                await self._persist_finish(
                    canonical_name,
                    status,
                    str(reason or ""),
                    done,
                    total,
                    state.get("last_error"),
                    completed_at,
                )

    # History & Recording
    def record_task(
        self,
        task: str,
        started_at: str | None,
        completed_at: str | None,
        status: str,
        reason: str = "",
        done: int = 0,
        total: int = 0,
        *,
        persist: bool = True,
    ) -> None:
        record: dict[str, Any] = {
            "task": task,
            "started_at": started_at,
            "completed_at": completed_at,
            "status": status,
            "reason": reason,
            "done": done,
            "total": total,
        }
        self.task_history.insert(0, record)
        if len(self.task_history) > _HISTORY_LIMIT:
            self.task_history = self.task_history[:_HISTORY_LIMIT]
        if persist and self.session_factory is not None:
            self._spawn_persist(
                self._persist_record(record), f"persist task record {task}"
            )

    @staticmethod
    def _history_key(record: dict[str, Any]) -> tuple[Any, ...]:
        return (
            record.get("task"),
            record.get("started_at"),
            record.get("completed_at"),
            record.get("status"),
        )

    def _merge_history(self, stored: Any, local: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge persisted and in-memory history, newest first and de-duplicated.

        ``persist_history`` used to overwrite the single ``AppConfig`` row with
        the process-local list, so concurrent workers finishing at the same time
        could lose each other's records (report 01 P3-9). Re-reading and merging
        before writing keeps foreign records intact.
        """
        merged: dict[tuple[Any, ...], dict[str, Any]] = {}
        candidates = list(stored or []) + list(local)
        for record in candidates:
            if not isinstance(record, dict):
                continue
            merged.setdefault(self._history_key(record), record)

        def _sort_key(record: dict[str, Any]) -> str:
            return str(record.get("completed_at") or record.get("started_at") or "")

        return sorted(merged.values(), key=_sort_key, reverse=True)[:_HISTORY_LIMIT]

    async def persist_history(self) -> None:
        from ..app.state import app_state

        session_cm = self.session_factory or app_state.session_factory
        if not session_cm:
            return
        try:
            from ..db.models import AppConfig

            async with session_cm() as session, session.begin():
                if hasattr(session, "get"):
                    row = await session.get(AppConfig, "task_history")
                else:
                    row = None
                stored = (
                    row.value.get("history")
                    if row is not None and isinstance(row.value, dict)
                    else None
                )
                merged = self._merge_history(stored, self.task_history)
                self.task_history = merged
                if row:
                    row.value = {"history": list(merged)}
                else:
                    session.add(AppConfig(key="task_history", value={"history": list(merged)}))
        except Exception as exc:  # noqa: BLE001
            logger.warning("failed to persist task history", extra={"error": str(exc)})

    async def restore_history(self) -> None:
        from ..app.state import app_state

        session_cm = self.session_factory or app_state.session_factory
        if not session_cm:
            return
        try:
            from ..db.models import AppConfig

            async with session_cm() as session:
                if hasattr(session, "get"):
                    row = await session.get(AppConfig, "task_history")
                else:
                    row = None
                if row and isinstance(row.value, dict) and "history" in row.value:
                    self.task_history.clear()
                    self.task_history.extend(row.value["history"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("failed to restore task history", extra={"error": str(exc)})

    def get_running_summary(self) -> list[dict[str, Any]]:
        running_tasks: list[dict[str, Any]] = []

        if self.scan_state.get("running"):
            running_tasks.append({
                "task": "scan",
                "started_at": self.scan_state.get("started_at"),
                "done": int(self.scan_state.get("scanned") or 0),
                "total": None,
                "stage": None,
                "cancellable": True,
            })
        if self.tag_sync_state.get("running"):
            running_tasks.append({
                "task": "tag-sync",
                "started_at": self.tag_sync_state.get("started_at"),
                "done": int(self.tag_sync_state.get("processed") or 0),
                "total": int(self.tag_sync_state.get("total") or 0),
                "stage": None,
                "cancellable": True,
            })
        if self.thumb_state.get("running"):
            running_tasks.append({
                "task": "thumbs",
                "started_at": self.thumb_state.get("started_at"),
                "done": int(self.thumb_state.get("succeeded") or 0) + int(self.thumb_state.get("failed") or 0),
                "total": int(self.thumb_state.get("total") or 0),
                "stage": None,
                "cancellable": True,
            })
        if self.metadata_sync_state.get("running"):
            running_tasks.append({
                "task": "metadata",
                "started_at": self.metadata_sync_state.get("started_at"),
                "done": int(self.metadata_sync_state.get("done") or 0),
                "total": int(self.metadata_sync_state.get("total") or 0),
                "stage": self.metadata_sync_state.get("stage"),
                "cancellable": True,
            })
        if self.favorites_check_state.get("running"):
            running_tasks.append({
                "task": "favorites-check",
                "started_at": self.favorites_check_state.get("started_at"),
                "done": sum(
                    int(item.get("done") or 0)
                    for item in self.favorites_check_state.get("categories", {}).values()
                    if isinstance(item, dict)
                ),
                "total": sum(
                    int(item.get("total") or 0)
                    for item in self.favorites_check_state.get("categories", {}).values()
                    if isinstance(item, dict)
                ),
                "stage": None,
                "cancellable": False,
            })
        if self.translation_state.get("running"):
            running_tasks.append({
                "task": "translation",
                "started_at": self.translation_state.get("started_at"),
                "done": int(self.translation_state.get("entries") or 0),
                "total": None,
                "stage": None,
                "cancellable": False,
            })
        if self.duplicates_state.get("running"):
            running_tasks.append({
                "task": "duplicates",
                "started_at": self.duplicates_state.get("started_at"),
                "done": self.duplicates_state.get("done", 0),
                "total": self.duplicates_state.get("total", 0),
                "stage": self.duplicates_state.get("stage"),
                "cancellable": False,
            })
        if self.gallery_updates_state.get("detecting"):
            running_tasks.append({
                "task": "gallery-updates",
                "started_at": self.gallery_updates_state.get("started_at") or self.gallery_updates_state.get("last_run"),
                "done": self.gallery_updates_state.get("found", 0),
                "total": None,
                "stage": "detecting",
                "cancellable": False,
            })
        if self.archive_state.get("running"):
            running_tasks.append({
                "task": "archive",
                "started_at": self.archive_state.get("started_at"),
                "done": int(self.archive_state.get("done") or 0),
                "total": int(self.archive_state.get("total") or 0),
                "stage": None,
                "cancellable": True,
            })
        if self.integrity_state.get("running"):
            running_tasks.append({
                "task": "integrity",
                "started_at": self.integrity_state.get("started_at"),
                "done": int(self.integrity_state.get("scanned") or 0),
                "total": int(self.integrity_state.get("total") or 0),
                "stage": None,
                "cancellable": False,
            })

        for name, d_state in self.dynamic_states.items():
            if d_state.get("running"):
                running_tasks.append({
                    "task": name,
                    "started_at": d_state.get("started_at"),
                    "done": int(d_state.get("done") or d_state.get("processed") or 0),
                    "total": int(d_state.get("total") or 0) if d_state.get("total") is not None else None,
                    "stage": d_state.get("stage"),
                    "cancellable": bool(d_state.get("cancellable", False)),
                })

        return running_tasks


default_task_manager = TaskManager()
