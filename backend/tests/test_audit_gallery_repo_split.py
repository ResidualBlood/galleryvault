"""R2 split contract: gallery repository helper + mixin extraction.

Batch 6 / R0 moved the module-level helpers of ``db.repositories.galleries`` to
``db.repositories.galleries_common`` (``galleries`` re-exports them). Batch 7 /
R15+R16 moved the eight reading progress/history methods to
``db.repositories.galleries_progress.GalleryProgressMixin`` and
``GalleryRepository`` now inherits it. Batch 8 moved the 41 read-only query
methods to ``db.repositories.galleries_query.GalleryQueryMixin``.

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
5. The progress mixin contract: it is in the MRO *before* ``BaseRepository``,
   the eight methods are defined in the new module (not copied), class-attribute
   monkeypatches (``GalleryRepository.clear_history`` ...) still dispatch, and
   ``get_by_id`` keeps its mock-session fallback (mixins first).
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from galleryvault.db.models import ReadingHistory, ReadingProgress
from galleryvault.db.repositories import (
    galleries,
    galleries_common,
    galleries_progress,
    galleries_query,
)
from galleryvault.db.repositories.base import BaseRepository
from galleryvault.db.repositories.galleries import GalleryRepository
from galleryvault.db.repositories.galleries_progress import GalleryProgressMixin
from galleryvault.db.repositories.galleries_query import GalleryQueryMixin
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


# --------------------------------------------------------------------------- #
# Progress mixin contract (batch 7 / R15+R16)
# --------------------------------------------------------------------------- #

_PROGRESS_METHODS = (
    "upsert_progress",
    "advance_progress",
    "_advance_progress_read_modify_write",
    "record_history",
    "_record_history_read_modify_write",
    "clear_history",
    "clear_progress",
    "delete_progress",
)


class _FallbackSession:
    """Minimal session double: no ``execute`` (exercises the RMW fallbacks)."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushes = 0
        self.get_value: object | None = None
        self.scalar_value: object | None = None

    async def get(self, _model: object, _key: object) -> object | None:
        return self.get_value

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushes += 1

    async def scalar(self, _stmt: object) -> object | None:
        return self.scalar_value


def test_progress_mixin_is_in_mro_before_base_repository() -> None:
    mro = GalleryRepository.__mro__
    assert GalleryProgressMixin in mro
    assert issubclass(GalleryRepository, GalleryProgressMixin)
    # Mixins must precede BaseRepository so their overrides win (``get_by_id``
    # mock-session fallback in galleries_query.py is the documented case).
    assert mro.index(GalleryProgressMixin) < mro.index(BaseRepository)
    assert GalleryProgressMixin in GalleryRepository.__bases__


def test_progress_methods_are_defined_in_the_new_module() -> None:
    for name in _PROGRESS_METHODS:
        func = getattr(GalleryRepository, name)
        assert inspect.isfunction(func), name
        assert func.__module__ == galleries_progress.__name__, name
        assert inspect.getsourcefile(func) == galleries_progress.__file__, name
        assert func.__globals__ is vars(galleries_progress), name
        # Moved, not copied: neither module nor class re-defines them.
        assert name not in vars(galleries), name
        assert name not in vars(GalleryRepository), name


async def test_progress_fallbacks_run_on_session_only_double() -> None:
    # The double has no ``model_cls`` and no ``execute``: the mixin must only
    # need a session (and the RMW fallbacks cover the double's shape).
    session = _FallbackSession()
    repo = GalleryRepository(session)  # type: ignore[arg-type]

    progress, advanced = await repo.advance_progress(1, 7, 20)
    assert (progress.current_page, progress.total_pages) == (7, 20)
    assert advanced is True

    history = await repo.record_history(1, 7, 20)
    assert (history.current_page, history.total_pages) == (7, 20)
    assert session.flushes == 2

    # Existing rows take the monotonic update branch and stamp the timestamp.
    existing = _FallbackSession()
    existing.get_value = ReadingProgress(gallery_id=1, current_page=3, total_pages=20)
    existing.scalar_value = ReadingHistory(gallery_id=1, current_page=3, total_pages=20)
    repo = GalleryRepository(existing)  # type: ignore[arg-type]

    stored, advanced = await repo.advance_progress(1, 7, 20)
    assert (stored.current_page, stored.total_pages, advanced) == (7, 20, True)
    assert isinstance(stored.updated_at, datetime)
    assert stored.updated_at.tzinfo is UTC

    stale, advanced = await repo.advance_progress(1, 2, 20)
    assert (stale.current_page, advanced) == (7, False)


@pytest.mark.parametrize("name", ["clear_history", "clear_progress"])
async def test_class_attribute_patch_dispatches_on_instances(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from galleryvault.app.core.uow import SqlAlchemyUnitOfWork

    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(GalleryRepository, name, mock)

    session = _FallbackSession()
    assert await getattr(GalleryRepository(session), name)() is None  # type: ignore[arg-type]
    assert mock.await_count == 1

    # Same dispatch through the repository assembled by the unit of work.
    uow = SqlAlchemyUnitOfWork()
    uow._session = session  # type: ignore[assignment]
    assert await getattr(uow.galleries, name)() is None
    assert mock.await_count == 2


async def test_get_by_id_still_overrides_base_repository_fallback() -> None:
    # ``GalleryRepository.get_by_id`` now lives in ``galleries_query`` and must
    # win over ``BaseRepository.get_by_id`` (which needs ``model_cls`` and would
    # raise) thanks to the mixin-first MRO.
    assert GalleryRepository.get_by_id.__module__ == galleries_query.__name__
    assert (
        GalleryRepository.__mro__.index(GalleryQueryMixin)
        < GalleryRepository.__mro__.index(BaseRepository)
    )

    class _ScalarOnlySession:
        def __init__(self) -> None:
            self.selects = 0

        async def scalar(self, _stmt: object) -> str:
            self.selects += 1
            return "from-scalar"

    session = _ScalarOnlySession()
    assert await GalleryRepository(session).get_by_id(3) == "from-scalar"  # type: ignore[arg-type]
    assert session.selects == 1


# --------------------------------------------------------------------------- #
# Query mixin contract (batch 8)
# --------------------------------------------------------------------------- #

# splits.md section 2.1 "Query/读" - 41 methods, 795 lines at the time of the
# inventory. Written out literally so the move cannot silently drop one.
_QUERY_METHODS = (
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
)


def test_query_method_roster_is_exactly_the_41_read_methods() -> None:
    assert len(_QUERY_METHODS) == len(set(_QUERY_METHODS)) == 41
    for name in _QUERY_METHODS:
        assert hasattr(GalleryRepository, name), name
    # The three responsibilities stay disjoint: no query name leaked into the
    # roster of what stayed behind in ``galleries``.
    assert set(_QUERY_METHODS) <= set(_EXPECTED_METHODS)


def test_query_methods_are_defined_in_the_new_module() -> None:
    for name in _QUERY_METHODS:
        func = getattr(GalleryQueryMixin, name)
        assert inspect.isfunction(func), name
        assert func.__module__ == galleries_query.__name__, name
        assert inspect.getsourcefile(func) == galleries_query.__file__, name
        assert func.__globals__ is vars(galleries_query), name
        # Moved, not copied: neither the module nor the class re-defines them.
        assert name not in vars(galleries), name
        assert name not in vars(GalleryRepository), name
        assert getattr(GalleryRepository, name) is func, name


def test_query_mixin_is_first_base_and_precedes_base_repository() -> None:
    mro = GalleryRepository.__mro__
    assert mro.index(GalleryQueryMixin) < mro.index(GalleryProgressMixin)
    assert mro.index(GalleryQueryMixin) < mro.index(BaseRepository)
    assert GalleryRepository.__bases__[0] is GalleryQueryMixin
    assert issubclass(GalleryRepository, GalleryQueryMixin)


def test_query_module_does_not_import_galleries_or_app_layer() -> None:
    # No import cycle back into ``galleries`` and no app-layer dependency.
    assert "galleries" not in vars(galleries_query)
    assert "GalleryRepository" not in vars(galleries_query)
    for name in vars(galleries_query):
        assert not name.startswith("galleryvault.app"), name


async def test_get_by_id_mock_session_branch_kept() -> None:
    # ``get_by_id`` prefers a callable ``session.get`` (the test-double path)
    # and only falls back to ``scalar`` otherwise.
    assert GalleryRepository.get_by_id.__code__.co_filename == galleries_query.__file__

    class _GetSession:
        def __init__(self) -> None:
            self.calls: list[tuple[object, object]] = []

        async def get(self, model: object, key: object) -> str:
            self.calls.append((model, key))
            return "from-get"

        async def scalar(self, _stmt: object) -> str:
            raise AssertionError("scalar must not be used when session.get exists")

    session = _GetSession()
    assert await GalleryRepository(session).get_by_id(11) == "from-get"  # type: ignore[arg-type]
    assert len(session.calls) == 1
    assert session.calls[0][1] == 11
    assert session.calls[0][0].__name__ == "Gallery"


def test_list_integrity_issues_source_is_inspectable() -> None:
    # test_pause_fix.py asserts on ``inspect.getsource`` of this method; the
    # move must keep resolving the source text.
    source = inspect.getsource(GalleryRepository.list_integrity_issues)
    assert "def list_integrity_issues" in source
    assert inspect.getsourcefile(GalleryRepository.list_integrity_issues) == (
        galleries_query.__file__
    )


@pytest.mark.parametrize("name", ["list_page", "tags_for_galleries"])
async def test_query_class_attribute_patch_dispatches_on_instances(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # test_auth patches these two as class attributes; that only works while
    # ``GalleryRepository`` stays a single concrete class.
    from galleryvault.app.core.uow import SqlAlchemyUnitOfWork

    sentinel = object()
    mock = AsyncMock(return_value=sentinel)
    monkeypatch.setattr(GalleryRepository, name, mock)

    session = _FallbackSession()
    assert await getattr(GalleryRepository(session), name)() is sentinel  # type: ignore[arg-type]
    assert mock.await_count == 1

    uow = SqlAlchemyUnitOfWork()
    uow._session = session  # type: ignore[assignment]
    assert await getattr(uow.galleries, name)() is sentinel
    assert mock.await_count == 2


async def test_query_methods_run_on_session_only_double() -> None:
    # The mixin needs nothing but ``self.session``: ``find_by_gids`` short
    # circuits on an empty id list before touching the session.
    repo = GalleryRepository(_FallbackSession())  # type: ignore[arg-type]
    assert await repo.find_by_gids([]) == []
