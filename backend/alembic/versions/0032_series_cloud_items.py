"""Add series_cloud_items table.

Additive only: table for linking series with un-downloaded cloud favorite items by gid.
"""

import sqlalchemy as sa

from alembic import op

revision = "0032_series_cloud_items"
down_revision = "0031_series"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "series_cloud_items",
        sa.Column("series_id", sa.BigInteger(), nullable=False),
        sa.Column("gid", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("series_id", "gid"),
        sa.UniqueConstraint("series_id", "gid"),
    )
    op.create_index(
        "idx_series_cloud_items_series_id", "series_cloud_items", ["series_id"]
    )
    op.create_index("idx_series_cloud_items_gid", "series_cloud_items", ["gid"])


def downgrade() -> None:
    op.drop_index("idx_series_cloud_items_gid", table_name="series_cloud_items")
    op.drop_index("idx_series_cloud_items_series_id", table_name="series_cloud_items")
    op.drop_table("series_cloud_items")
