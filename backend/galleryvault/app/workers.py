"""Supervised registry for background workers.

Long-lived loops (downloads, ingest pump, favorites poll, cookie health, ...)
must never stop silently.  ``WorkerRegistry`` owns their tasks, restarts them
with exponential backoff whenever they crash *or* return unexpectedly, and
bounds shutdown so a stuck worker cannot block engine disposal forever.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal

from ..logging import log_extra

logger = logging.getLogger(__name__)

RestartPolicy = Literal["always", "once"]

DEFAULT_INITIAL_RESTART_DELAY = 1.0
DEFAULT_MAX_RESTART_DELAY = 60.0
DEFAULT_SHUTDOWN_TIMEOUT = 10.0


async def supervise_worker(
    name: str,
    factory: Callable[[], Awaitable[None]],
    *,
    restart_policy: RestartPolicy = "always",
    initial_delay: float = DEFAULT_INITIAL_RESTART_DELAY,
    max_delay: float = DEFAULT_MAX_RESTART_DELAY,
    is_stopping: Callable[[], bool] | None = None,
) -> None:
    """Run ``factory`` until cancelled, honouring ``restart_policy``.

    ``always`` workers restart after an exception *and* after a normal return
    (both with backoff); a normal return is logged as a warning because a
    long-lived loop that exits means its precondition disappeared.  ``once``
    workers run exactly once and only restart after a crash.

    A worker may swallow ``CancelledError`` and return normally (several loops
    do).  Before treating that as an unexpected exit we check whether this task
    has a pending cancellation request or the registry is stopping, and raise
    ``CancelledError`` instead of logging/restarting.
    """
    loop = asyncio.get_running_loop()
    delay = max(0.0, initial_delay)
    while True:
        started = loop.time()
        try:
            await factory()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if _cancellation_requested(is_stopping):
                raise asyncio.CancelledError from None
            delay = _delay_after_run(loop.time() - started, delay, initial_delay, max_delay)
            logger.exception(
                "background worker crashed; restarting with backoff",
                extra=log_extra(worker=name, error=type(exc).__name__, retry_in=delay),
            )
            await asyncio.sleep(delay)
            delay = min(max(delay * 2, initial_delay), max_delay)
            continue

        if _cancellation_requested(is_stopping):
            raise asyncio.CancelledError

        if restart_policy == "once":
            logger.info("background worker finished", extra=log_extra(worker=name))
            return

        delay = _delay_after_run(loop.time() - started, delay, initial_delay, max_delay)
        logger.warning(
            "background worker returned unexpectedly; restarting with backoff",
            extra=log_extra(worker=name, retry_in=delay),
        )
        await asyncio.sleep(delay)
        delay = min(max(delay * 2, initial_delay), max_delay)


def _cancellation_requested(is_stopping: Callable[[], bool] | None) -> bool:
    """True when this task was cancelled or the registry started shutting down."""
    task = asyncio.current_task()
    if task is not None and task.cancelling() > 0:
        return True
    return bool(is_stopping is not None and is_stopping())


def _delay_after_run(
    run_duration: float,
    delay: float,
    initial_delay: float,
    max_delay: float,
) -> float:
    """Reset backoff after a healthy run long enough to count as steady state."""
    if run_duration >= max_delay:
        return max(0.0, initial_delay)
    return delay


@dataclass
class WorkerSpec:
    """Registration record for one supervised worker."""

    name: str
    factory: Callable[[], Awaitable[None]]
    restart_policy: RestartPolicy = "always"
    shutdown_timeout: float = DEFAULT_SHUTDOWN_TIMEOUT
    initial_delay: float = DEFAULT_INITIAL_RESTART_DELAY
    max_delay: float = DEFAULT_MAX_RESTART_DELAY
    task: asyncio.Task[None] | None = field(default=None, repr=False)


class WorkerRegistry:
    """Owns the tasks of all long-lived background workers."""

    def __init__(self, *, default_shutdown_timeout: float = DEFAULT_SHUTDOWN_TIMEOUT) -> None:
        self._workers: dict[str, WorkerSpec] = {}
        self._default_shutdown_timeout = default_shutdown_timeout
        self._stopping = False

    def register(
        self,
        name: str,
        factory: Callable[[], Awaitable[None]],
        *,
        restart_policy: RestartPolicy = "always",
        shutdown_timeout: float | None = None,
        initial_delay: float = DEFAULT_INITIAL_RESTART_DELAY,
        max_delay: float = DEFAULT_MAX_RESTART_DELAY,
    ) -> WorkerSpec:
        """Register (or replace) a worker without starting it."""
        spec = WorkerSpec(
            name=name,
            factory=factory,
            restart_policy=restart_policy,
            shutdown_timeout=(
                self._default_shutdown_timeout if shutdown_timeout is None else shutdown_timeout
            ),
            initial_delay=initial_delay,
            max_delay=max_delay,
        )
        self._workers[name] = spec
        return spec

    def start(self, name: str) -> asyncio.Task[None] | None:
        """Start a registered worker; returns ``None`` outside an event loop."""
        spec = self._workers.get(name)
        if spec is None:
            raise KeyError(f"worker {name!r} is not registered")
        if spec.task is not None and not spec.task.done():
            return spec.task
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        task = loop.create_task(
            supervise_worker(
                spec.name,
                spec.factory,
                restart_policy=spec.restart_policy,
                initial_delay=spec.initial_delay,
                max_delay=spec.max_delay,
                is_stopping=lambda: self._stopping,
            ),
            name=f"worker:{spec.name}",
        )
        spec.task = task
        return task

    def start_all(self) -> None:
        """Start every registered worker that is not already running."""
        for name in list(self._workers):
            self.start(name)

    def ensure(
        self,
        name: str,
        factory: Callable[[], Awaitable[None]],
        *,
        restart_policy: RestartPolicy = "always",
        shutdown_timeout: float | None = None,
        initial_delay: float = DEFAULT_INITIAL_RESTART_DELAY,
        max_delay: float = DEFAULT_MAX_RESTART_DELAY,
    ) -> asyncio.Task[None] | None:
        """Register ``name`` if needed and return its running task.

        A finished ``once`` task or a crashed worker is started again; this
        keeps runtime settings refreshes idempotent.
        """
        spec = self._workers.get(name)
        if spec is None:
            self.register(
                name,
                factory,
                restart_policy=restart_policy,
                shutdown_timeout=shutdown_timeout,
                initial_delay=initial_delay,
                max_delay=max_delay,
            )
        else:
            spec.factory = factory
            spec.restart_policy = restart_policy
            if shutdown_timeout is not None:
                spec.shutdown_timeout = shutdown_timeout
            if spec.task is not None and not spec.task.done():
                return spec.task
        return self.start(name)

    def get_task(self, name: str) -> asyncio.Task[None] | None:
        spec = self._workers.get(name)
        return None if spec is None else spec.task

    def is_running(self, name: str) -> bool:
        task = self.get_task(name)
        return task is not None and not task.done()

    def running_names(self) -> list[str]:
        return [name for name in self._workers if self.is_running(name)]

    def stop(self, name: str) -> None:
        task = self.get_task(name)
        if task is not None and not task.done():
            task.cancel()

    def clear(self) -> None:
        """Drop all registrations, cancelling any tasks still running."""
        for spec in self._workers.values():
            task = spec.task
            if task is not None and not task.done():
                with contextlib.suppress(RuntimeError):
                    task.cancel()
        self._workers.clear()
        self._stopping = False

    async def shutdown(
        self,
        *,
        timeout: float | None = None,
        extra_tasks: Iterable[asyncio.Task] = (),
    ) -> None:
        """Cancel workers and wait at most ``timeout`` seconds for them.

        Tasks that outlive the wait are logged as warnings and deliberately
        left behind so the caller can continue disposing the engine.
        """
        named: dict[asyncio.Task, str] = {
            spec.task: spec.name
            for spec in self._workers.values()
            if spec.task is not None and not spec.task.done()
        }
        for task in extra_tasks:
            if task is not None and not task.done():
                named.setdefault(task, task.get_name() if hasattr(task, "get_name") else "task")
        if not named:
            return

        self._stopping = True
        if timeout is None:
            timeout = max(
                (
                    self._workers[name].shutdown_timeout
                    for name in named.values()
                    if name in self._workers
                ),
                default=self._default_shutdown_timeout,
            )

        tasks = set(named)
        for task in tasks:
            task.cancel()
        _done, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in pending:
            logger.warning(
                "background worker did not stop within shutdown timeout; "
                "continuing shutdown",
                extra=log_extra(worker=named.get(task, "task"), timeout=timeout),
            )
