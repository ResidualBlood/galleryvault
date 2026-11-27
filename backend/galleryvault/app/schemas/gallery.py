"""Gallery response models (list, recycle bin, integrity, detail).

These models are the single declaration of the gallery payload shape.  The
routers build the payloads with ``serialize_gallery_summary()`` /
``serialize_gallery_detail()`` and FastAPI validates/filters them through these
models, so a field can never be dropped or renamed by accident.  The key set is
pinned by ``tests/contract/golden/*.json``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GalleryTag(BaseModel):
    """Tag preview attached to a gallery row or a resolved query."""

    namespace: str | None = None
    name: str
    display: str


class GalleryPageItem(BaseModel):
    """One page of a gallery detail response."""

    index: int
    page_index: int
    name: str | None = None
    member_name: str | None = None
    media_type: str | None = None
    image_url: str
    thumb_url: str


class GallerySummary(BaseModel):
    """Gallery row as returned by ``GET /api/galleries``."""

    id: int
    gid: int | None = None
    token: str | None = None
    title: str
    title_english: str | None = None
    title_jpn: str | None = None
    storage_type: str | None = None
    storage_tier: str = "hot"
    cold_at: str | None = None
    category: str = "other"
    page_count: int = 0
    cover_url: str | None = None
    tags: list[GalleryTag] = Field(default_factory=list)
    tag_count: int = 0
    uploader: str | None = None
    posted_at: str | None = None
    file_size: int | None = None
    storage_size: int | None = None
    rating: float | None = None
    favorite: bool = False
    favorite_category: int | None = None
    reading_progress: int | None = None
    expunged: bool = False
    image_quality: str | None = None
    local_rating: int | None = None
    local_note: str | None = None


class GalleryListResponse(BaseModel):
    """Envelope of ``GET /api/galleries``."""

    total: int = 0
    page: int = 1
    page_size: int = 24
    q: str | None = None
    tags: str = ""
    resolved: bool = False
    tag_mode: str = "or"
    tag_match: str = "exact"
    order_by: str | None = None
    read_status: str = "all"
    category: str = ""
    query_tags: list[GalleryTag] = Field(default_factory=list)
    items: list[GallerySummary] = Field(default_factory=list)


class GalleryDetail(BaseModel):
    """Full gallery payload of ``GET /api/galleries/{identifier}``.

    Declared standalone rather than as a ``GallerySummary`` subclass: the
    detail payload intentionally has no ``cover_url`` / ``tag_count``, and
    inheriting them would re-add those keys to the response.
    """

    id: int
    gid: int | None = None
    token: str | None = None
    title: str
    title_english: str | None = None
    title_jpn: str | None = None
    storage_type: str | None = None
    storage_tier: str = "hot"
    cold_at: str | None = None
    category: str = "other"
    page_count: int = 0
    file_size: int | None = None
    storage_size: int | None = None
    uploader: str | None = None
    posted_at: str | None = None
    rating: float | None = None
    favorite: bool = False
    favorite_category: int | None = None
    reading_progress: int | None = None
    expunged: bool = False
    image_quality: str | None = None
    local_rating: int | None = None
    local_note: str | None = None
    storage_path: str = ""
    eh_url: str | None = None
    exhentai_url: str | None = None
    warnings: list[Any] = Field(default_factory=list)
    spider_info: dict[str, Any] = Field(default_factory=dict)
    source_meta: dict[str, Any] = Field(default_factory=dict)
    tags: list[GalleryTag] = Field(default_factory=list)
    tags_synced_at: datetime | None = None
    pages: list[GalleryPageItem] = Field(default_factory=list)


class GalleryTrashItem(BaseModel):
    """Row of ``GET /api/galleries/trash``."""

    id: int
    gid: int | None = None
    token: str | None = None
    title: str
    title_jpn: str | None = None
    category: str = "other"
    page_count: int = 0
    cover_url: str | None = None
    trashed_at: str | None = None
    storage_path: str = ""
    tags: list[GalleryTag] = Field(default_factory=list)
    tag_count: int = 0
    reading_progress: int | None = None


class GalleryTrashResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 24
    items: list[GalleryTrashItem] = Field(default_factory=list)


class GalleryExpungedItem(BaseModel):
    """Row of ``GET /api/galleries/expunged``."""

    id: int
    gid: int | None = None
    token: str | None = None
    title: str
    page_count: int = 0
    cover_url: str | None = None
    updated_at: str | None = None
    storage_path: str = ""
    tags: list[GalleryTag] = Field(default_factory=list)
    tag_count: int = 0


class GalleryExpungedResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 24
    items: list[GalleryExpungedItem] = Field(default_factory=list)


class MagicScanSummary(BaseModel):
    """Last integrity magic-byte scan counters."""

    running: bool = False
    started_at: str | None = None
    completed_at: str | None = None
    scanned: int = 0
    total: int = 0
    corrupt: int = 0


class GalleryIntegrityItem(BaseModel):
    """Row of ``GET /api/galleries/integrity``."""

    id: int
    gid: int | None = None
    title: str
    page_count: int = 0
    actual_pages: int = 0
    file_count: int | None = None
    cover_url: str | None = None
    storage_path: str = ""
    tags: list[GalleryTag] = Field(default_factory=list)


class GalleryIntegrityResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 24
    magic_scan: MagicScanSummary = Field(default_factory=MagicScanSummary)
    items: list[GalleryIntegrityItem] = Field(default_factory=list)
