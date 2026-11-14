"""Response models for the gallery-updates endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GalleryUpdateItem(BaseModel):
    """Row of ``GET /api/updates`` (also ``/api/updates/ignored``)."""

    id: int
    gallery_id: int
    old_gid: int
    new_gid: int
    title: str
    favcat: int
    favcat_name: str = ""
    status: str
    error_message: str | None = None
    detected_at: str | None = None
    updated_at: str | None = None
    cover_url: str | None = None
    match_source: str | None = None
    new_title: str | None = None
    old_page_count: int | None = None
    new_page_count: int | None = None
    ambiguous: bool = False
    ambiguous_count: int = 1


class GalleryUpdatesListResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 24
    state: str = "active"
    items: list[GalleryUpdateItem] = Field(default_factory=list)
