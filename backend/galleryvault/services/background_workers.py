"""Unified worker execution context and lifecycle management for background workflows."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from ..app.core.uow import SqlAlchemyUnitOfWork, UnitOfWork
from ..config import Settings, get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from ..app.core.eh_client_manager import EhClientManager
    from ..app.core.task_dispatcher import TaskDispatcher

logger = logging.getLogger(__name__)


class WorkerState(str, Enum):
    """Execution state of a managed background worker."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class WorkerContext:
    """Unified execution context for background workers.

    Decouples workers from global singletons (like app_state) by explicitly
    injecting session factories, settings, client managers, and cancellation tokens.
    """

    session_factory: async_sessionmaker[AsyncSession] | None = None
    settings: Settings | None = None
    eh_client_manager: EhClientManager | None = None
    task_dispatcher: TaskDispatcher | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    extra: dict[str, Any] = field(default_factory=dict)

    def create_uow(self) -> UnitOfWork:
        """Create a dedicated UnitOfWork instance using the injected session_factory."""
        if self.session_factory is None:
            raise RuntimeError("Cannot create UnitOfWork: session_factory is not provided in WorkerContext")
        return SqlAlchemyUnitOfWork(self.session_factory)

    def is_cancelled(self) -> bool:
        """Check if worker termination was requested."""
        return self.stop_event.is_set()

    def cancel(self) -> None:
        """Request worker termination."""
        self.stop_event.set()

    async def wait_or_cancel(self, timeout: float) -> bool:
        """Wait for `timeout` seconds or until cancellation is requested.

        Returns:
            True if the timeout completed normally without cancellation.
            False if worker cancellation was triggered.
        """
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=timeout)
            return False
        except TimeoutError:
            return True

    def record_task_audit(
        self,
        action: str,
        target: str,
        status: str = "success",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record task execution details via the injected TaskDispatcher."""
        if self.task_dispatcher is not None:
            self.task_dispatcher.record_task_and_persist(
                action=action,
                target=target,
                status=status,
                details=details,
            )


class WorkerLifecycleManager:
    """Manages background worker tasks lifecycle, status tracking, and graceful shutdown."""

    def __init__(self, default_context: WorkerContext | None = None) -> None:
        self.default_context = default_context
        self._workers: dict[str, asyncio.Task[Any]] = {}
        self._contexts: dict[str, WorkerContext] = {}
        self._states: dict[str, WorkerState] = {}
        self._errors: dict[str, str | None] = {}

    def register_and_start(
        self,
        name: str,
        worker_coro_fn: Callable[[WorkerContext], Coroutine[Any, Any, None]],
        context: WorkerContext | None = None,
    ) -> asyncio.Task[Any]:
        """Register and start a background worker with its execution context."""
        if name in self._workers and not self._workers[name].done():
            self.stop_worker(name)

        ctx = context or self.default_context
        if ctx is None:
            ctx = WorkerContext()
        ctx.stop_event = asyncio.Event()

        self._contexts[name] = ctx
        self._states[name] = WorkerState.RUNNING
        self._errors[name] = None

        async def _wrapper() -> None:
            try:
                await worker_coro_fn(ctx)
                self._states[name] = WorkerState.STOPPED
            except asyncio.CancelledError:
                self._states[name] = WorkerState.STOPPED
                logger.info("Worker %s was cancelled", name)
            except Exception as exc:
                self._states[name] = WorkerState.ERROR
                self._errors[name] = str(exc)
                logger.exception("Worker %s encountered unhandled error", name)

        task = asyncio.create_task(_wrapper(), name=f"worker-{name}")
        self._workers[name] = task
        return task

    def stop_worker(self, name: str) -> None:
        """Signal a specific worker to stop and cancel its task."""
        ctx = self._contexts.get(name)
        if ctx is not None:
            ctx.cancel()
        task = self._workers.get(name)
        if task is not None and not task.done():
            task.cancel()
            self._states[name] = WorkerState.STOPPING

    def stop_all(self) -> None:
        """Signal all managed workers to terminate."""
        for name in list(self._workers.keys()):
            self.stop_worker(name)

    def get_status(self, name: str) -> dict[str, Any] | None:
        """Retrieve status details for a specific worker."""
        if name not in self._workers:
            return None
        task = self._workers[name]
        return {
            "name": name,
            "state": self._states.get(name, WorkerState.IDLE).value,
            "done": task.done(),
            "cancelled": task.cancelled(),
            "error": self._errors.get(name),
        }

    def list_statuses(self) -> dict[str, dict[str, Any]]:
        """List statuses of all managed workers."""
        return {
            name: st for name in self._workers if (st := self.get_status(name)) is not None
        }


def create_worker_context(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    settings: Settings | None = None,
    eh_client_manager: EhClientManager | None = None,
    task_dispatcher: TaskDispatcher | None = None,
    **extra: Any,
) -> WorkerContext:
    """Convenience factory function for assembling a WorkerContext."""
    return WorkerContext(
        session_factory=session_factory,
        settings=settings or get_settings(),
        eh_client_manager=eh_client_manager,
        task_dispatcher=task_dispatcher,
        extra=dict(extra),
    )


__all__ = [
    "WorkerContext",
    "WorkerLifecycleManager",
    "WorkerState",
    "create_worker_context",
]
