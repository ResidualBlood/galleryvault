import asyncio
import logging
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from ..app.core.task_dispatcher import TaskDispatcher
from ..app.core.uow import UnitOfWork


class BaseService:
    """Base service providing explicit UnitOfWork transaction lifecycle,

    task dispatching, and audit logging without depending on global state.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        task_dispatcher: TaskDispatcher | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.uow = uow
        self.task_dispatcher = task_dispatcher
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[UnitOfWork]:
        """Context manager wrapping an explicit UnitOfWork transaction.

        Usage:
            async with self.transaction() as uow:
                ...
        """
        async with self.uow as uow_instance:
            yield uow_instance

    def spawn_background_task(
        self,
        name: str,
        coro: Coroutine[Any, Any, Any],
        **kwargs: Any,
    ) -> asyncio.Task | None:
        """Spawn an asynchronous background task via TaskDispatcher if configured."""
        if self.task_dispatcher is not None:
            return self.task_dispatcher.spawn(name, coro, **kwargs)
        self.logger.info("Spawning standalone task without TaskDispatcher: %s", name)
        return asyncio.create_task(coro)

    async def record_task_audit(
        self,
        task_type: str = "unknown",
        status: str = "completed",
        message: str = "",
        details: dict[str, Any] | None = None,
        *,
        action: str | None = None,
        reason: str | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Record task execution details to persistent history / audit store."""
        resolved_task_type = (
            action
            or name
            or (task_type if task_type != "unknown" else None)
            or kwargs.pop("task", None)
            or "unknown"
        )
        payload = dict(details or {})
        for k, v in kwargs.items():
            payload.setdefault(k, v)

        effective_message = message or reason or ""
        effective_reason = reason if reason is not None else (message or None)

        if self.task_dispatcher is not None:
            await self.task_dispatcher.record_task_and_persist(
                task_type=resolved_task_type,
                status=status,
                message=effective_message,
                details=payload,
                reason=effective_reason,
                **kwargs,
            )
        else:
            self.logger.info(
                "Task audit [%s] (%s): %s | %s",
                resolved_task_type,
                status,
                effective_message,
                payload,
            )

    @asynccontextmanager
    async def audit_scope(
        self,
        task_type: str,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Scope context manager recording audit log upon completion or failure."""
        payload = dict(details or {})
        if self.task_dispatcher is not None:
            async with self.task_dispatcher.audit_scope(
                task_type=task_type,
                message=message,
                details=payload,
            ):
                yield payload
        else:
            self.logger.info("Entering audit scope [%s]: %s", task_type, message)
            try:
                yield payload
                self.logger.info("Completed audit scope [%s]", task_type)
            except Exception:
                self.logger.exception("Failed audit scope [%s]", task_type)
                raise
