"""Cache gdata gallery metadata keyed by gid.

The favorite monitor already walks every favorite and fetches full metadata via
the batched gdata API; storing it lets a gallery scanned onto disk reuse tags,
title, category and posted date without another per-gallery ExHentai fetch.
"""

import sqlalchemy as sa

from alembic import op

revision = "0013_gallery_metadata"
down_revision = "0012_favorite_file_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gallery_metadata",
        sa.Column("gid", sa.BigInteger(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("title_jpn", sa.Text(), nullable=True),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("uploader", sa.String(128), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expunged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tags", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("gallery_metadata")
