"""Shared helpers and constants for the cold archive package.

The split keeps the historical logger name so existing log filters and tests
that watch ``galleryvault.services.cold_archive`` keep working.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from ...app.state import app_state
from ...config import get_settings
from ..downloader import _truncate_utf8 as truncate_utf8
from ..export_cbz import ZIP_STORED, page_archive_name

__all__ = [
    "ZIP_STORED",
    "logger",
    "page_archive_name",
    "truncate_utf8",
]

logger = logging.getLogger("galleryvault.services.cold_archive")


_IGNORED_NAMES = {
    "cover.jpg",
    "cover.jpeg",
    "cover.png",
    "cover.webp",
    ".ehviewer",
    "metadata",
    "metadata.json",
    "comicinfo.xml",
    ".galleryvault.json",
    "thumbs.db",
    ".ds_store",
}


def _clear_gallery_thumbs(gallery_id: int) -> None:
    """Clear thumbnail cache directory for a gallery if pages changed."""
    if app_state.thumbnail_service is not None:
        thumb_dir = app_state.thumbnail_service.root / str(gallery_id)
    else:
        settings = app_state.settings or get_settings()
        root = Path(getattr(settings, "thumbnail_cache_dir", "/gv-cache/thumbs"))
        thumb_dir = root / str(gallery_id)

    if thumb_dir.exists():
        try:
            if thumb_dir.is_dir():
                shutil.rmtree(thumb_dir, ignore_errors=True)
            else:
                thumb_dir.unlink(missing_ok=True)
            logger.info("Cleared thumbnail cache for gallery %s at %s", gallery_id, thumb_dir)
        except OSError as exc:
            logger.warning("Failed to clear thumbnail cache for gallery %s: %s", gallery_id, exc)
