"""Compatibility facade for the split :mod:`galleryvault.services.download` package.

All implementation now lives in ``services/download/{wake,notify,ingest_pump,
attempt,worker}.py``. This module only re-exports the names other modules and
tests have always imported; it must not grow new logic.
"""

from __future__ import annotations

from ..db.repository import DownloadRepository
from .download.attempt import (
    _CHALLENGE_PROBE_INTERVAL,
    _challenge_counts,
    _resume_challenge_pause,
    _run_download_inner,
    _trigger_challenge_pause,
    challenge_count,
    challenge_probe_loop,
    clear_download_cancelled,
    is_download_cancelled,
    mark_download_cancelled,
    reset_challenge_count,
    retry_backoff,
    run_download,
)
from .download.ingest_pump import (
    _INGEST_PAYLOAD_FIELDS,
    IngestError,
    _archive_downloaded_gallery,
    _scan_running,
    infer_image_quality,
    ingest_downloaded_gallery,
    ingest_pump_loop,
    ingest_result_from_payload,
    maybe_scan_after_download,
    run_pending_ingest_once,
    serialize_ingest_payload,
)
from .download.notify import (
    download_progress,
    record_download_notification,
    telegram_flush_loop,
)
from .download.wake import _worker_events, notify_new_task, pool
from .download.worker import (
    _WORKER_POLL_MAX_SECONDS,
    _WORKER_POLL_MIN_SECONDS,
    _download_worker,
    _idle_poll_timeout,
    adjust_download_concurrency,
    download_worker_loop,
    stop_download_workers,
)

__all__ = [
    "_CHALLENGE_PROBE_INTERVAL",
    "_INGEST_PAYLOAD_FIELDS",
    "_WORKER_POLL_MAX_SECONDS",
    "_WORKER_POLL_MIN_SECONDS",
    "DownloadRepository",
    "IngestError",
    "_archive_downloaded_gallery",
    "_challenge_counts",
    "_download_worker",
    "_idle_poll_timeout",
    "_resume_challenge_pause",
    "_run_download_inner",
    "_scan_running",
    "_trigger_challenge_pause",
    "_worker_events",
    "adjust_download_concurrency",
    "challenge_count",
    "challenge_probe_loop",
    "clear_download_cancelled",
    "download_progress",
    "download_worker_loop",
    "infer_image_quality",
    "ingest_downloaded_gallery",
    "ingest_pump_loop",
    "ingest_result_from_payload",
    "is_download_cancelled",
    "mark_download_cancelled",
    "maybe_scan_after_download",
    "notify_new_task",
    "pool",
    "record_download_notification",
    "reset_challenge_count",
    "retry_backoff",
    "run_download",
    "run_pending_ingest_once",
    "serialize_ingest_payload",
    "stop_download_workers",
    "telegram_flush_loop",
]
