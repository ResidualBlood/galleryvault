"""Add series_cloud_exclusions table.

Additive only: table for recording cloud favorite items excluded from series.
"""

import sqlalchemy as sa

from alembic import op

revision = "0033_series_cloud_exclusions"
down_revision = "0032_series_cloud_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "series_cloud_exclusions",
        sa.Column("series_id", sa.BigInteger(), nullable=False),
        sa.Column("gid", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("series_id", "gid"),
        sa.UniqueConstraint("series_id", "gid"),
    )
    op.create_index(
        "idx_series_cloud_exclusions_series_id",
        "series_cloud_exclusions",
        ["series_id"],
    )
    op.create_index(
        "idx_series_cloud_exclusions_gid",
        "series_cloud_exclusions",
        ["gid"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_series_cloud_exclusions_gid", table_name="series_cloud_exclusions"
    )
    op.drop_index(
        "idx_series_cloud_exclusions_series_id",
        table_name="series_cloud_exclusions",
    )
    op.drop_table("series_cloud_exclusions")
