"""Add online_reading_progress for galleries that are not in the local library.

Online galleries are identified by their ExHentai ``gid`` only, so they cannot
reuse ``reading_progress`` (primary key ``gallery_id`` foreign-keyed to
``galleries.id``). The new table stores the page counter plus the gallery
identity/thumbnail metadata needed to render the online history list; resolved
page-image URLs are never persisted.

Revision ID: 0042_online_reading_progress
Revises: 0041_backfill_gallery_uploader
Create Date: 2026-11-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0042_online_reading_progress"
down_revision = "0041_backfill_gallery_uploader"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "online_reading_progress",
        sa.Column("gid", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("thumb", sa.Text(), nullable=True),
        sa.Column("current_page", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_pages", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("gid"),
    )
    op.create_index(
        "idx_online_reading_progress_updated",
        "online_reading_progress",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_online_reading_progress_updated", table_name="online_reading_progress")
    op.drop_table("online_reading_progress")
