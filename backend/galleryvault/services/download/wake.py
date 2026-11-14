"""Wake-up signalling shared by the download workers and the ingest pump."""

from __future__ import annotations

import asyncio
from typing import Any

from ...app.state import app_state

_worker_events: set[asyncio.Event] = set()


def _get_background_session_factory() -> Any:
    return getattr(app_state, "background_session_factory", None) or app_state.session_factory


def notify_new_task() -> None:
    """Wake up download workers when a new task is enqueued or retried."""
    for ev in list(_worker_events):
        ev.set()
