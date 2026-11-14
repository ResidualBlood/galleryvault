"""Legacy facade for the cold archive service package.

All implementation lives in :mod:`galleryvault.services.cold`; this module only
re-exports the historical public surface so existing importers keep working.
"""

from __future__ import annotations

from ..storage_paths import is_under_cold, resolve_archive_roots
from .cold import (
    COLD_ARCHIVE_MAX_CBZ_BYTES,
    COLD_ARCHIVE_MAX_CBZ_PAGES,
    ColdAlreadyArchivedError,
    ColdDestinationExistsError,
    ColdStorageError,
    _check_physically_archived,
    _cold_path_filter,
    _extract_cold_pack,
    _extract_source_meta,
    _normalize_root_prefix,
    _validate_cold_destination,
    archive_one,
    build_comic_info_xml,
    build_galleryvault_json,
    cold_copy_covers_source,
    cold_pack_gallery,
    cold_partition,
    compute_cold_path,
    purge_archived_sources_internal,
    reconcile_storage_tier,
    run_cold_archive,
    run_purge_archived_sources,
    run_unarchive,
    safe_title,
    select_archive_root,
    unarchive_one,
)

__all__ = [
    "COLD_ARCHIVE_MAX_CBZ_BYTES",
    "COLD_ARCHIVE_MAX_CBZ_PAGES",
    "ColdAlreadyArchivedError",
    "ColdDestinationExistsError",
    "ColdStorageError",
    "_check_physically_archived",
    "_cold_path_filter",
    "_extract_cold_pack",
    "_extract_source_meta",
    "_normalize_root_prefix",
    "_validate_cold_destination",
    "archive_one",
    "build_comic_info_xml",
    "build_galleryvault_json",
    "cold_copy_covers_source",
    "cold_pack_gallery",
    "cold_partition",
    "compute_cold_path",
    "is_under_cold",
    "purge_archived_sources_internal",
    "reconcile_storage_tier",
    "resolve_archive_roots",
    "run_cold_archive",
    "run_purge_archived_sources",
    "run_unarchive",
    "safe_title",
    "select_archive_root",
    "unarchive_one",
]
