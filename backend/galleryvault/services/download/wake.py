"""Wake-up signalling shared by the download workers and the ingest pump."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ...app.state import app_state


@dataclass
class DownloadWorkerPool:
    """Mutable download-worker state owned by the module-level ``pool`` singleton.

    Kept in one object so the wake signals, live tasks and target concurrency
    can never drift apart between modules.
    """

    events: set[asyncio.Event] = field(default_factory=set)
    tasks: list[asyncio.Task] = field(default_factory=list)
    target: int = 2


pool = DownloadWorkerPool()

# Backwards-compatible alias for the same mutable set object. Never rebound.
_worker_events = pool.events


def _get_background_session_factory() -> Any:
    return getattr(app_state, "background_session_factory", None) or app_state.session_factory


def notify_new_task() -> None:
    """Wake up download workers when a new task is enqueued or retried."""
    for ev in list(pool.events):
        ev.set()
