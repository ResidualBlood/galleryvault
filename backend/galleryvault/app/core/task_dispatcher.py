"""Task dispatcher and background audit execution coordinator."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from ...logging import log_extra

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """Dispatches background tasks, coordinates audit history, and tracks task lifecycle."""

    def __init__(
        self,
        task_manager_getter: Callable[[], Any] | None = None,
    ) -> None:
        self._task_manager_getter = task_manager_getter
        self._active_tasks: set[asyncio.Task[Any]] = set()

    @property
    def task_manager(self) -> Any | None:
        if self._task_manager_getter is not None:
            return self._task_manager_getter()
        from ..state import app_state

        return app_state.task_manager

    def spawn(
        self,
        coroutine: Coroutine[Any, Any, Any],
        operation: str = "background_operation",
    ) -> asyncio.Task[Any] | None:
        """Safely spawn a fire-and-forget coroutine with error logging and lifetime tracking."""

        async def guarded() -> None:
            try:
                await coroutine
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Background task failed",
                    extra=log_extra(operation=operation, error=type(exc).__name__, message=str(exc)),
                )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if hasattr(coroutine, "close"):
                coroutine.close()
            return None

        task = loop.create_task(guarded(), name=operation)
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

        try:
            from ..state import app_state

            spawned = app_state.extra.get("spawned_tasks")
            if isinstance(spawned, set):
                spawned.add(task)
                task.add_done_callback(spawned.discard)
        except Exception:  # noqa: BLE001, S110
            pass

        return task

    async def record_task_and_persist(
        self,
        task_type: str = "unknown",
        status: str = "completed",
        message: str = "",
        details: dict[str, Any] | None = None,
        *,
        reason: str | None = None,
        entity_type: str | None = None,
        entity_id: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Record an audit task and trigger history persistence."""
        tm = self.task_manager
        if tm is None:
            return

        if task_type == "unknown" and "action" in kwargs:
            task_type = str(kwargs.pop("action"))

        payload = dict(details or {})
        if entity_type is not None:
            payload["entity_type"] = entity_type
        if entity_id is not None:
            payload["entity_id"] = str(entity_id)
        if reason is not None:
            payload.setdefault("reason", reason)
        for k, v in kwargs.items():
            if k not in ("started_at", "completed_at"):
                payload.setdefault(k, v)

        effective_reason = reason if reason is not None else (message or "")
        now = datetime.now(UTC).isoformat()
        started_at = kwargs.get("started_at", now)
        completed_at = kwargs.get("completed_at", now)
        done = int(kwargs.get("done", 0) or 0)
        total = int(kwargs.get("total", 0) or 0)

        try:
            if hasattr(tm, "record_task"):
                try:
                    sig = inspect.signature(tm.record_task)
                    if "started_at" in sig.parameters:
                        tm.record_task(
                            task=task_type,
                            started_at=started_at,
                            completed_at=completed_at,
                            status=status,
                            reason=effective_reason,
                            done=done,
                            total=total,
                        )
                    else:
                        tm.record_task(task_type, status, message, payload)
                except (TypeError, ValueError):
                    try:
                        tm.record_task(
                            task=task_type,
                            started_at=started_at,
                            completed_at=completed_at,
                            status=status,
                            reason=effective_reason,
                            done=done,
                            total=total,
                        )
                    except TypeError:
                        tm.record_task(task_type, status, message, payload)
            if hasattr(tm, "persist_history"):
                res = tm.persist_history()
                if hasattr(res, "__await__"):
                    await res
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to record or persist task history",
                extra=log_extra(task_type=task_type, error=str(exc)),
            )

    def spawn_record_task(
        self,
        task_type: str = "unknown",
        status: str = "completed",
        message: str = "",
        details: dict[str, Any] | None = None,
        *,
        reason: str | None = None,
        entity_type: str | None = None,
        entity_id: Any | None = None,
        **kwargs: Any,
    ) -> asyncio.Task[Any] | None:
        """Spawn task recording and history persistence in the background non-blockingly."""
        return self.spawn(
            self.record_task_and_persist(
                task_type,
                status=status,
                message=message,
                details=details,
                reason=reason,
                entity_type=entity_type,
                entity_id=entity_id,
                **kwargs,
            ),
            operation=f"record_task:{task_type}",
        )

    @asynccontextmanager
    async def audit_scope(
        self,
        task_type: str,
        operation_name: str,
        details: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Context manager to automatically record start, success, or failure audit history."""
        context_details = dict(details or {})
        try:
            yield context_details
            self.spawn_record_task(
                task_type=task_type,
                status="completed",
                message=f"{operation_name} completed successfully",
                details=context_details,
            )
        except Exception as exc:
            context_details["error"] = str(exc)
            context_details["error_type"] = type(exc).__name__
            self.spawn_record_task(
                task_type=task_type,
                status="failed",
                message=f"{operation_name} failed: {exc}",
                details=context_details,
            )
            raise

    def get_active_tasks(self) -> set[asyncio.Task[Any]]:
        """Return a snapshot of currently running active tasks."""
        return set(self._active_tasks)

    def cancel_all(self) -> None:
        """Cancel all currently tracked active tasks."""
        for task in list(self._active_tasks):
            if not task.done():
                task.cancel()
