"""Pydantic request and response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..services.duplicate_resolver import DUPLICATE_POLICIES
from ..services.eh_client import parse_gallery_url


class DownloadRequest(BaseModel):
    url: str | None = None
    gid: int | None = Field(default=None, gt=0)
    token: str | None = None
    title: str | None = None
    mode: str | None = None
    max_pages: int | None = Field(default=None, gt=0)
    quality: str | None = None

    @model_validator(mode="after")
    def valid_source(self) -> DownloadRequest:
        if self.quality is not None and self.quality not in {"original", "resample"}:
            raise ValueError("quality must be 'original' or 'resample'")
        if self.url:
            try:
                gid, token = parse_gallery_url(self.url)
            except (ValueError, TypeError) as exc:
                raise ValueError(str(exc)) from exc
            object.__setattr__(self, "gid", gid)
            object.__setattr__(self, "token", token)
        if not self.gid or not self.token:
            raise ValueError("url or gid and token is required")
        return self


class FavoriteCategoryRequest(BaseModel):
    favcat: int | None = Field(default=None, ge=0, le=9)
    enabled: bool | None = None
    mode: str | None = None


class FavoritesRemoveRequest(BaseModel):
    gids: list[int] = Field(default_factory=list)
    delete_local: bool = False
    items: list[dict[str, Any]] = Field(default_factory=list)
    delete_files: bool = False
    delete_all_copies: bool = False

    @model_validator(mode="after")
    def populate_gids(self) -> FavoritesRemoveRequest:
        if not self.gids and self.items:
            extracted: list[int] = []
            for it in self.items:
                if isinstance(it, dict) and "gid" in it:
                    try:
                        extracted.append(int(it["gid"]))
                    except (ValueError, TypeError):
                        pass
            object.__setattr__(self, "gids", extracted)
        if self.delete_files:
            object.__setattr__(self, "delete_local", True)
        elif self.delete_local:
            object.__setattr__(self, "delete_files", True)
        return self


class FavoritesMoveRequest(BaseModel):
    gids: list[int] = Field(default_factory=list)
    target_favcat: int = Field(..., ge=0, le=9)
    items: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def populate_gids(self) -> FavoritesMoveRequest:
        if not self.gids and self.items:
            extracted: list[int] = []
            for it in self.items:
                if isinstance(it, dict) and "gid" in it:
                    try:
                        extracted.append(int(it["gid"]))
                    except (ValueError, TypeError):
                        pass
            object.__setattr__(self, "gids", extracted)
        return self


class FavoritesAddRequest(BaseModel):
    gid: int | None = None
    token: str | None = None
    target_favcat: int = Field(default=0, ge=0, le=9)
    note: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def populate_items(self) -> FavoritesAddRequest:
        if self.gid is not None and not self.items:
            object.__setattr__(
                self, "items", [{"gid": self.gid, "token": self.token, "note": self.note}]
            )
        return self


class ArchivePreviewRequest(BaseModel):
    gids: list[int]


class DownloadSelectedRequest(BaseModel):
    gids: list[int]
    archive: bool = False
    quality: str | None = None


class DuplicateIgnoreRequest(BaseModel):
    key: str
    title: str | None = None
    gids: list[int] = Field(default_factory=list)


class ProgressRequest(BaseModel):
    current_page: int = Field(default=0, ge=0)
    total_pages: int | None = Field(default=None, ge=0)
    page: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def sync_page(self) -> ProgressRequest:
        if self.page is not None and self.current_page == 0:
            object.__setattr__(self, "current_page", self.page)
        elif self.current_page is not None and self.page is None:
            object.__setattr__(self, "page", self.current_page)
        return self


class BulkDeleteRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)
    gallery_ids: list[int] = Field(default_factory=list)
    delete_files: bool = False
    delete_all_copies: bool = False

    @model_validator(mode="after")
    def sync_ids(self) -> BulkDeleteRequest:
        if not self.ids and self.gallery_ids:
            object.__setattr__(self, "ids", list(self.gallery_ids))
        elif not self.gallery_ids and self.ids:
            object.__setattr__(self, "gallery_ids", list(self.ids))
        return self


class FilteredDeleteRequest(BaseModel):
    q: str = ""
    category: str | None = None
    tags: str | None = None
    tag: str | None = None
    tag_mode: str = "or"
    tag_match: str = "exact"
    delete_files: bool = False
    delete_all_copies: bool = False
    uploader: str | None = None
    min_rating: float | None = None
    favorite: bool | None = None
    read: bool | None = None
    expunged: bool | None = None
    min_pages: int | None = None
    max_pages: int | None = None
    media_type: str | None = None
    storage_type: str | None = None
    min_posted_at: str | None = None
    max_posted_at: str | None = None
    read_status: str | None = None
    order_by: str | None = None
    exclude_tags: str | None = None

    @model_validator(mode="after")
    def sync_tags(self) -> FilteredDeleteRequest:
        if not self.tags and self.tag:
            object.__setattr__(self, "tags", self.tag)
        elif not self.tag and self.tags:
            object.__setattr__(self, "tag", self.tags)
        return self


class UpdateIdsRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)
    archive: bool = False
    quality: str | None = None


class DownloadOriginalRequest(BaseModel):
    archive: bool = False


class SettingsRequest(BaseModel):
    library_roots: list[str] | str | None = None
    exhentai_base_url: str | None = None
    exhentai_cookies: dict[str, str] | None = None
    http_proxy: str | None = None
    socks5_proxy: str | None = None
    download_root: str | None = None
    download_concurrency: int | None = Field(default=None, ge=1, le=32)
    page_concurrency: int | None = Field(default=None, ge=1, le=16)
    download_quality: str | None = None
    download_title: str | None = None
    archive_quality: str | None = None
    favorites_archive_enabled: bool | None = None
    favorites_archive_max_pages: int | None = Field(default=None, ge=0)
    archive_fallback_pages: bool | None = None
    use_hah: bool | None = None
    image_download_timeout_seconds: int | None = Field(default=None, ge=1)
    image_slow_warmup_seconds: int | None = Field(default=None, ge=1)
    image_min_speed_kb_s: int | None = Field(default=None, ge=1)
    title_display: str | None = None
    favorites_categories: list[int] | None = None
    download_favorites_enabled: bool | None = None
    favorites_poll_interval_minutes: int | None = Field(default=None, ge=1)
    favorites: list[dict[str, Any]] | None = None
    ipb_member_id: str | None = None
    ipb_pass_hash: str | None = None
    igneous: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_ids: list[str] | None = None
    telegram_allowed_user_ids: list[int] | None = None
    telegram_notify_level: str | None = None
    telegram_notify_lang: str | None = None
    auto_sync_tags: bool | None = None
    tag_sync_interval_seconds: float | None = Field(default=None, gt=0)
    tag_sync_concurrency: int | None = Field(default=None, ge=1, le=32)
    generate_thumbnails: bool | None = None
    duplicate_policy: str | None = None
    auth_required: bool | None = None
    trusted_proxies: list[str] | None = None
    tag_translation_update_interval_minutes: int | None = Field(default=None, ge=0)
    global_paused: bool | None = None

    @model_validator(mode="after")
    def validate_values(self) -> SettingsRequest:
        if self.http_proxy and self.socks5_proxy:
            raise ValueError("configure only one proxy")
        if self.favorites_categories is not None and any(
            category not in range(10) for category in self.favorites_categories
        ):
            raise ValueError("favorites categories must be between 0 and 9")
        if self.telegram_notify_level is not None and self.telegram_notify_level not in {
            "summary",
            "immediate",
            "failures_only",
            "off",
        }:
            raise ValueError(
                "telegram_notify_level must be 'summary', 'immediate', 'failures_only', or 'off'"
            )
        if self.telegram_notify_lang is not None and self.telegram_notify_lang not in {"zh", "en"}:
            raise ValueError("telegram_notify_lang must be 'zh' or 'en'")
        if self.duplicate_policy is not None and self.duplicate_policy not in DUPLICATE_POLICIES:
            raise ValueError(
                f"duplicate_policy must be one of {', '.join(DUPLICATE_POLICIES)}"
            )
        return self


class LogLevelRequest(BaseModel):
    level: str = Field(..., description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")

    @model_validator(mode="after")
    def validate_level(self) -> LogLevelRequest:
        lvl = self.level.upper()
        if lvl not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        self.level = lvl
        return self

