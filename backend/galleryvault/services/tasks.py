"""Unified background task state machine and registry."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


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

    def __init__(self, task_name: str, state: dict[str, Any]):
        self.task_name = task_name
        self.state = state

    def update(self, **kwargs: Any) -> None:
        self.state.update(kwargs)

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

    # Cancellation flags
    def request_cancel(self, task_key: str | int) -> None:
        self._cancelled_tasks.add(task_key)

    def clear_cancelled(self, task_key: str | int) -> None:
        self._cancelled_tasks.discard(task_key)

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

        tracker = TaskTracker(task_name, state)
        status = "success"
        reason = ""
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
                canonical_name = "favorites-check" if task_name in ("favcheck", "favorites-check") else task_name

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
                        )
                        try:
                            from ..app.dependencies import spawn_task

                            spawn_task(self.persist_history(), "persist task history")
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("failed to spawn persist task history", extra={"error": str(exc)})

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
        if len(self.task_history) > 200:
            self.task_history = self.task_history[:200]

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
                if row:
                    row.value = {"history": list(self.task_history)}
                else:
                    session.add(AppConfig(key="task_history", value={"history": list(self.task_history)}))
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
