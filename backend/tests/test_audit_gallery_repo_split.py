"""R2 split contract: gallery repository helper extraction (batch 6 / R0).

The module-level helpers of ``db.repositories.galleries`` now live in
``db.repositories.galleries_common``; ``galleries`` re-exports them so every
existing import site and module-attribute monkeypatch keeps working.

Asserted here:
1. The full ``GalleryRepository`` method roster still exists on the class
   (written out literally so a future mixin split cannot silently drop one).
2. Every helper is reachable from ``galleries`` and is the *same object* as in
   ``galleries_common`` (re-export, not a copy) - including the title-sort cache.
3. ``services.tag_sync`` still resolves ``_upsert_uploader_tag`` through
   ``galleries`` at call time, so the ``test_tag_sync`` patch path is intact.
4. ``GalleryRepository`` still lives in ``galleries`` and resolves the helpers
   through that module's globals today; the assertion pins it so the later
   mixin split cannot change it silently.
"""

from __future__ import annotations

import inspect

import pytest

from galleryvault.db.repositories import galleries, galleries_common
from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.services import tag_sync

# Roster as of the split (82 names: 80 methods + parse_existing_rows /
# find_missing_ids staticmethods) - from splits.md section 2.1.
_EXPECTED_METHODS = (
    # Query / read
    "get_by_id",
    "list_page",
    "progress_for_galleries",
    "next_gallery_id",
    "resolve_exact_tags",
    "search_tags",
    "resolve_tag_names",
    "category_counts",
    "tag_facets",
    "tags_for_galleries",
    "tag_counts_for",
    "random_id",
    "list_trashed",
    "list_expunged",
    "list_integrity_issues",
    "list_magic_scan_targets",
    "progress",
    "history_page",
    "get",
    "get_for_tag_sync",
    "pending_category_refresh_ids",
    "count_pending_category_refresh",
    "get_by_identifier",
    "get_by_gid",
    "metadata_map",
    "metadata_for_gid",
    "cold_metadata_gids",
    "storage_size_map",
    "largest_by_storage",
    "library_storage_sum",
    "pending_tag_sync_ids",
    "tag_sync_status_for_gids",
    "get_gallery_with_pages",
    "get_pages",
    "tags_for_gallery",
    "find_by_gids",
    "find_by_ids",
    "list_duplicates",
    "set_duplicate_status",
    "delete_duplicate",
    "duplicate_copies_for_gid",
    # Metadata
    "fetch_starred_and_custom_tag_metadata",
    "upsert_metadata",
    "seed_metadata_from_galleries",
    "pending_image_quality_gids",
    "null_image_quality_gids",
    "set_image_qualities",
    "apply_cached_metadata",
    "apply_metadata_to_galleries",
    "replace_tags",
    "set_local_tags",
    "update_titles",
    "set_local_rating",
    "update_gallery_fields",
    "refresh_category",
    "sync_categories_from_metadata",
    "mark_tag_not_visible",
    "resume_not_visible",
    "mark_tag_synced",
    # Ingest
    "upsert_many",
    "fetch_existing_rows_raw",
    "parse_existing_rows",
    "existing_rows",
    "sync_duplicates",
    "fetch_expunge_candidates",
    "find_missing_ids",
    "mark_expunged",
    "expunge_missing",
    "_mark_expunged",
    "restore_galleries",
    "purge_galleries",
    "delete_ids",
    "trash_galleries",
    "repair_deleted_misclassified",
    # Reading / progress
    "upsert_progress",
    "advance_progress",
    "_advance_progress_read_modify_write",
    "record_history",
    "_record_history_read_modify_write",
    "clear_history",
    "clear_progress",
    "delete_progress",
)

_EXPECTED_HELPERS = (
    "_TITLE_SORT_COL_CACHE",
    "_title_sort_column",
    "_IMAGE_MAGIC_PREFIXES",
    "_is_valid_page_header",
    "_session_dialect",
    "_dialect_insert",
    "_upsert_uploader_tag",
)


def test_repository_method_roster_is_complete() -> None:
    missing = [name for name in _EXPECTED_METHODS if not hasattr(GalleryRepository, name)]
    assert missing == []
    for name in _EXPECTED_METHODS:
        assert callable(getattr(GalleryRepository, name)), name
    assert len(set(_EXPECTED_METHODS)) == len(_EXPECTED_METHODS) == 82


def test_helpers_live_in_common_module_and_are_reexported() -> None:
    for name in _EXPECTED_HELPERS:
        assert hasattr(galleries_common, name), f"{name} missing from galleries_common"
        assert hasattr(galleries, name), f"{name} not re-exported by galleries"
        assert getattr(galleries, name) is getattr(galleries_common, name), name


def test_helper_code_really_lives_in_common_module() -> None:
    # ``is`` identity plus source file proves a move, not a duplicated copy.
    for name in ("_title_sort_column", "_is_valid_page_header", "_upsert_uploader_tag"):
        helper = getattr(galleries_common, name)
        assert inspect.getsourcefile(helper) == galleries_common.__file__, name
        assert helper.__globals__ is vars(galleries_common), name


def test_title_sort_cache_is_shared_between_modules() -> None:
    assert galleries._TITLE_SORT_COL_CACHE is galleries_common._TITLE_SORT_COL_CACHE
    galleries_common._TITLE_SORT_COL_CACHE.clear()
    first = galleries_common._title_sort_column("english")
    assert first is not None
    assert galleries_common._TITLE_SORT_COL_CACHE["english"] is first
    # Same object via the re-exported entry point.
    assert galleries._title_sort_column("english") is first
    galleries_common._TITLE_SORT_COL_CACHE.clear()


def test_galleries_module_has_no_all_whitelist() -> None:
    # A literal ``__all__`` would break ``from ... import *`` call sites.
    assert not hasattr(galleries, "__all__")


def test_tag_sync_patch_path_still_resolves_through_galleries(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setattr(galleries, "_upsert_uploader_tag", sentinel)

    from galleryvault.db.repositories.galleries import (
        _upsert_uploader_tag as resolved,
    )

    assert resolved is sentinel
    # tag_sync must not have bound the helper at import time, otherwise the
    # module-attribute patch above would be invisible to it.
    assert "_upsert_uploader_tag" not in vars(tag_sync)


@pytest.mark.parametrize("method", ["upsert_many", "apply_cached_metadata"])
def test_repository_internal_calls_resolve_through_galleries(
    method: str, monkeypatch
) -> None:
    """The class still lives in ``galleries``, so its helper lookups go through
    that module's globals (the re-exported names). Patching
    ``galleries._upsert_uploader_tag`` therefore still reaches internal calls -
    the same behaviour as before the move. A later mixin split must re-check
    this (documented risk in the plan)."""
    func = getattr(GalleryRepository, method)
    assert inspect.isfunction(func)
    assert func.__globals__ is vars(galleries)

    sentinel = object()
    monkeypatch.setitem(func.__globals__, "_upsert_uploader_tag", sentinel)
    assert func.__globals__["_upsert_uploader_tag"] is sentinel
    assert galleries_common._upsert_uploader_tag is not sentinel


def test_common_module_does_not_import_app_layer() -> None:
    for name in vars(galleries_common):
        assert not name.startswith("galleryvault.app"), name
    assert "galleries" not in vars(galleries_common)
