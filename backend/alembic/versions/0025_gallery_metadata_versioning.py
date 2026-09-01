"""Add versioning and replacement markers to gallery_metadata.

Additive only: records parent and newer-version gids plus replacement status
discovered from ExHentai gallery pages and gdata, allowing the library and updates
workers to track lineage across re-uploads and multi-part series without re-fetching.
"""

import sqlalchemy as sa

from alembic import op

revision = "0025_gallery_metadata_versioning"
down_revision = "0024_gallery_image_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gallery_metadata",
        sa.Column("parent_gid", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "gallery_metadata",
        sa.Column("newer_gid", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "gallery_metadata",
        sa.Column("is_replaced", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("gallery_metadata", "is_replaced")
    op.drop_column("gallery_metadata", "newer_gid")
    op.drop_column("gallery_metadata", "parent_gid")
