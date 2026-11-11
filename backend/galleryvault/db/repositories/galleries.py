"""Assembled ``GalleryRepository`` (mixins split, batch 10 / R11-R14+R17).

The repository body was moved to four focused mixins; this module keeps the
single concrete class, its ``__init__`` and the re-exports that existing import
sites rely on:

* ``db.repositories.galleries.GalleryRepository`` - same object, so
  class-attribute monkeypatches and ``isinstance`` keep working.
* module-level helpers from :mod:`galleries_common` (``_title_sort_column``,
  ``_upsert_uploader_tag``, ...) - ``services.integrity_worker`` and
  ``services.tag_sync`` import them from here; ``tag_sync`` re-imports
  ``_upsert_uploader_tag`` at call time so patching this module still works.

No ``__all__``: a literal whitelist would break ``from ... import *`` sites.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Gallery
from .base import BaseRepository
from .galleries_common import (  # noqa: F401
    _IMAGE_MAGIC_PREFIXES,
    _TITLE_SORT_COL_CACHE,
    _dialect_insert,
    _is_valid_page_header,
    _session_dialect,
    _title_sort_column,
    _upsert_uploader_tag,
)
from .galleries_ingest import GalleryIngestMixin
from .galleries_metadata import GalleryMetadataMixin
from .galleries_progress import GalleryProgressMixin
from .galleries_query import GalleryQueryMixin


class GalleryRepository(
    GalleryQueryMixin,
    GalleryMetadataMixin,
    GalleryIngestMixin,
    GalleryProgressMixin,
    BaseRepository[Gallery],
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Gallery)
