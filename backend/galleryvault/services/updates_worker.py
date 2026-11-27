"""Compatibility facade for the gallery-updates maintain modules.

The detect/normalize/finalize clusters now live in
``galleryvault.services.maintain`` (``updates_normalize``, ``updates_detect``,
``updates_finalize``).  This module only re-exports the public names so
existing imports keep working (CR1); new code should import the maintain
modules directly.
"""

from __future__ import annotations

from ..db.repository import DownloadRepository, GalleryUpdatesRepository
from .download_worker import notify_new_task
from .maintain.updates_detect import detect_gallery_updates, run_gallery_updates
from .maintain.updates_finalize import (
    FINALIZE_WAIT_LIMIT,
    _finalize_wait_counts,
    finalize_gallery_update,
    finalize_updates_for_new_gid,
    gallery_updates_finalize_loop,
    record_gallery_update_log,
)
from .maintain.updates_normalize import normalize_update_title

__all__ = [
    "FINALIZE_WAIT_LIMIT",
    "DownloadRepository",
    "GalleryUpdatesRepository",
    "_finalize_wait_counts",
    "detect_gallery_updates",
    "finalize_gallery_update",
    "finalize_updates_for_new_gid",
    "gallery_updates_finalize_loop",
    "normalize_update_title",
    "notify_new_task",
    "record_gallery_update_log",
    "run_gallery_updates",
]
