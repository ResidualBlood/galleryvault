"""Database repositories facade.

This module re-exports all domain repositories from ``galleryvault.db.repositories``
for 100% backwards-compatibility.
"""

from .repositories import (
    _CHUNK_SIZE,
    BackgroundJobsRepository,
    DownloadRepository,
    FavoritesRepository,
    GalleryRepository,
    GalleryUpdatesRepository,
    SettingsRepository,
    _chunked,
    escape_like_wildcards,
    path_hash,
)

__all__ = [
    "_CHUNK_SIZE",
    "BackgroundJobsRepository",
    "DownloadRepository",
    "FavoritesRepository",
    "GalleryRepository",
    "GalleryUpdatesRepository",
    "SettingsRepository",
    "_chunked",
    "escape_like_wildcards",
    "path_hash",
]
