"""Cold archive storage package.

Modules are split by responsibility; the legacy
:mod:`galleryvault.services.cold_archive` facade re-exports this public surface.
"""

from __future__ import annotations

from .orchestrate import (
    archive_one,
    purge_archived_sources_internal,
    reconcile_storage_tier,
    run_cold_archive,
    run_purge_archived_sources,
)
from .pack import (
    COLD_ARCHIVE_MAX_CBZ_BYTES,
    COLD_ARCHIVE_MAX_CBZ_PAGES,
    ColdAlreadyArchivedError,
    ColdDestinationExistsError,
    ColdStorageError,
    _extract_source_meta,
    cold_pack_gallery,
)
from .paths import (
    _cold_path_filter,
    _normalize_root_prefix,
    build_comic_info_xml,
    build_galleryvault_json,
    cold_partition,
    compute_cold_path,
    safe_title,
    select_archive_root,
)
from .restore import _extract_cold_pack, run_unarchive, unarchive_one
from .verify import (
    _check_physically_archived,
    _validate_cold_destination,
    cold_copy_covers_source,
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
    "purge_archived_sources_internal",
    "reconcile_storage_tier",
    "run_cold_archive",
    "run_purge_archived_sources",
    "run_unarchive",
    "safe_title",
    "select_archive_root",
    "unarchive_one",
]
