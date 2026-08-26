from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Gallery(Base):
    __tablename__ = "galleries"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    gid: Mapped[int | None] = mapped_column(BigInteger)
    token: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    title_jpn: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(32))
    uploader: Mapped[str | None] = mapped_column(String(128))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_count: Mapped[int | None] = mapped_column(Integer)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    rating: Mapped[float | None] = mapped_column(Float)
    expunged: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_type: Mapped[str] = mapped_column(String(16))
    storage_path: Mapped[str] = mapped_column(Text)
    path_hash: Mapped[str] = mapped_column(String(64))
    storage_mtime_ns: Mapped[int | None] = mapped_column(BigInteger)
    storage_size: Mapped[int | None] = mapped_column(BigInteger)
    storage_signature: Mapped[str] = mapped_column(String(64))
    cover_path: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    source_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    tags_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("idx_galleries_gid", "gid", unique=True, postgresql_where=text("gid IS NOT NULL")),
        Index("idx_galleries_path_hash", "path_hash"),
        Index("idx_galleries_tags_synced_at", "tags_synced_at"),
        Index("idx_galleries_storage_type", "storage_type"),
        Index("idx_galleries_posted_at", "posted_at"),
    )


class GalleryPage(Base):
    __tablename__ = "gallery_pages"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    gallery_id: Mapped[int] = mapped_column(ForeignKey("galleries.id", ondelete="CASCADE"))
    page_index: Mapped[int] = mapped_column(Integer)
    member_name: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(16))
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("gallery_id", "page_index"),
        Index("idx_gallery_pages_gallery_id", "gallery_id"),
    )


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("namespace", "name"),
        Index(
            "idx_tags_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class GalleryTag(Base):
    __tablename__ = "gallery_tags"
    gallery_id: Mapped[int] = mapped_column(
        ForeignKey("galleries.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (Index("idx_gallery_tags_tag_id", "tag_id", "gallery_id"),)


class DownloadTask(Base):
    __tablename__ = "download_tasks"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    gid: Mapped[int] = mapped_column(BigInteger)
    token: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    mode: Mapped[str | None] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(32))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    max_pages: Mapped[int | None] = mapped_column(Integer)
    current_page: Mapped[int] = mapped_column(Integer, default=0)
    total_pages: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    target_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "idx_download_tasks_active_gid",
            "gid",
            unique=True,
            postgresql_where=text("status IN ('pending', 'downloading')"),
        ),
        CheckConstraint(
            "status IN ('pending', 'downloading', 'success', 'failed', 'cancelled')",
            name="ck_download_task_status",
        ),
        CheckConstraint("max_retries BETWEEN 0 AND 3", name="ck_download_task_max_retries"),
    )


class FavoritesMonitor(Base):
    __tablename__ = "favorites_monitor"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    favcat: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mode: Mapped[str] = mapped_column(String(16), default="incremental")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=43200)


class FavoriteItem(Base):
    __tablename__ = "favorite_items"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    favcat: Mapped[int] = mapped_column(Integer, nullable=False)
    gid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("favcat", "gid"),
        Index("idx_favorite_items_gid", "gid"),
    )


class GalleryMetadata(Base):
    """Cached ExHentai metadata for a gid, filled from the gdata batch API.

    Lets a gallery scanned onto disk reuse tags/title/category/posted without
    another per-gallery ExHentai fetch: ingest and tag-sync look here first.
    """

    __tablename__ = "gallery_metadata"
    gid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    token: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(Text)
    title_jpn: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(32))
    uploader: Mapped[str | None] = mapped_column(String(128))
    file_count: Mapped[int | None] = mapped_column(Integer)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    rating: Mapped[float | None] = mapped_column(Float)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expunged: Mapped[bool] = mapped_column(Boolean, default=False)
    thumb: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[Any] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DuplicateIgnore(Base):
    """User-marked duplicate groups that should not be reported again.

    Keyed by the group key (``artist|normalized_title``) produced by the
    duplicate scan, so the manager can hide false positives permanently.
    """

    __tablename__ = "favorite_duplicate_ignores"
    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    title: Mapped[str | None] = mapped_column(Text)
    gids: Mapped[list[int] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AppConfig(Base):
    __tablename__ = "app_config"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    gallery_id: Mapped[int] = mapped_column(
        ForeignKey("galleries.id", ondelete="CASCADE"), primary_key=True
    )
    current_page: Mapped[int] = mapped_column(Integer, default=0)
    total_pages: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReadingHistory(Base):
    __tablename__ = "reading_history"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    gallery_id: Mapped[int] = mapped_column(ForeignKey("galleries.id", ondelete="CASCADE"))
    current_page: Mapped[int] = mapped_column(Integer, default=0)
    total_pages: Mapped[int | None] = mapped_column(Integer)
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("gallery_id"),
        Index("idx_reading_history_last_read", "last_read_at"),
    )


class FavoritesCheckLog(Base):
    __tablename__ = "favorites_check_logs"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    favcat: Mapped[int] = mapped_column(Integer, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    discovered_gids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (Index("idx_favorites_check_logs_category", "favcat", "checked_at"),)


class DownloadAttempt(Base):
    __tablename__ = "download_attempts"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("download_tasks.id", ondelete="CASCADE"))
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("idx_download_attempts_task", "task_id"),)
