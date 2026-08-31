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
    items: list[dict[str, Any]]
    delete_files: bool = False
    delete_all_copies: bool = False


class DuplicateIgnoreRequest(BaseModel):
    key: str
    title: str | None = None
    gids: list[int] = Field(default_factory=list)


class ProgressRequest(BaseModel):
    page: int = Field(ge=0)


class BulkDeleteRequest(BaseModel):
    gallery_ids: list[int] = Field(default_factory=list)
    delete_files: bool = False
    delete_all_copies: bool = False


class FilteredDeleteRequest(BaseModel):
    delete_files: bool = False
    delete_all_copies: bool = False
    q: str | None = None
    category: str | None = None
    tag: str | None = None
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
