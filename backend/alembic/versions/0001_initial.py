"""Initial GalleryVault schema."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "galleries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("gid", sa.BigInteger()),
        sa.Column("token", sa.String(64)),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_jpn", sa.Text()),
        sa.Column("category", sa.String(32)),
        sa.Column("uploader", sa.String(128)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("file_count", sa.Integer()),
        sa.Column("file_size", sa.BigInteger()),
        sa.Column("rating", sa.Float()),
        sa.Column("expunged", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("storage_type", sa.String(16), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("path_hash", sa.String(64), nullable=False),
        sa.Column("storage_mtime_ns", sa.BigInteger()),
        sa.Column("storage_size", sa.BigInteger()),
        sa.Column("storage_signature", sa.String(64), nullable=False),
        sa.Column("cover_path", sa.Text()),
        sa.Column("page_count", sa.Integer()),
        sa.Column("source_meta", postgresql.JSONB()),
        sa.Column("tags_synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_galleries_gid",
        "galleries",
        ["gid"],
        unique=True,
        postgresql_where=sa.text("gid IS NOT NULL"),
    )
    op.create_index("idx_galleries_path_hash", "galleries", ["path_hash"])
    op.create_index("idx_galleries_storage_type", "galleries", ["storage_type"])
    op.create_index("idx_galleries_posted_at", "galleries", ["posted_at"])
    op.execute(
        "CREATE INDEX idx_galleries_title_fts ON galleries USING GIN (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(title_jpn, '')))"
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("namespace", sa.String(32), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("namespace", "name"),
    )
    op.create_index(
        "idx_tags_name_trgm",
        "tags",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "gallery_pages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "gallery_id",
            sa.BigInteger(),
            sa.ForeignKey("galleries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("member_name", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("manifest", postgresql.JSONB()),
        sa.UniqueConstraint("gallery_id", "page_index"),
    )
    op.create_index("idx_gallery_pages_gallery_id", "gallery_pages", ["gallery_id"])

    op.create_table(
        "gallery_tags",
        sa.Column(
            "gallery_id",
            sa.BigInteger(),
            sa.ForeignKey("galleries.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.BigInteger(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("idx_gallery_tags_tag_id", "gallery_tags", ["tag_id", "gallery_id"])

    op.create_table(
        "download_tasks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("gid", sa.BigInteger(), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("mode", sa.String(16)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_message", sa.Text()),
        sa.Column("target_path", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_download_tasks_status", "download_tasks", ["status"])
    op.create_index("idx_download_tasks_gid", "download_tasks", ["gid"])

    op.create_table(
        "favorites_monitor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("favcat", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.String(128)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("mode", sa.String(16), nullable=False, server_default="incremental"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "reading_progress",
        sa.Column(
            "gallery_id",
            sa.BigInteger(),
            sa.ForeignKey("galleries.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("current_page", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_pages", sa.Integer()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in [
        "reading_progress",
        "app_config",
        "favorites_monitor",
        "download_tasks",
        "gallery_tags",
        "gallery_pages",
        "tags",
        "galleries",
    ]:
        op.drop_table(table)
