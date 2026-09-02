"""Unified background task state machine and registry."""

from __future__ import annotations

import logging
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

    # Cancellation flags
    def request_cancel(self, task_key: str | int) -> None:
        self._cancelled_tasks.add(task_key)

    def clear_cancelled(self, task_key: str | int) -> None:
        self._cancelled_tasks.discard(task_key)

    def is_cancelled(self, task_key: str | int) -> bool:
        return task_key in self._cancelled_tasks

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
                "task": "favcheck",
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
                "started_at": None,
                "done": self.duplicates_state.get("done", 0),
                "total": self.duplicates_state.get("total", 0),
                "stage": self.duplicates_state.get("stage"),
                "cancellable": False,
            })
        if self.gallery_updates_state.get("detecting"):
            running_tasks.append({
                "task": "gallery-updates",
                "started_at": self.gallery_updates_state.get("last_run"),
                "done": self.gallery_updates_state.get("found", 0),
                "total": None,
                "stage": "detecting",
                "cancellable": False,
            })

        return running_tasks


default_task_manager = TaskManager()
