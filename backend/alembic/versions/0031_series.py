"""Add series, series_items, and series_exclusions tables.

Additive only: new tables for grouping related galleries into series.
"""

import sqlalchemy as sa

from alembic import op

revision = "0031_series"
down_revision = "0030_favmon_enabled_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("match_key", sa.String(length=512), nullable=True),
        sa.Column("name_manual", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_key"),
    )
    op.create_table(
        "series_items",
        sa.Column("series_id", sa.BigInteger(), nullable=False),
        sa.Column("gallery_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=16), server_default=sa.text("'auto'"), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["gallery_id"], ["galleries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("gallery_id"),
        sa.UniqueConstraint("gallery_id"),
    )
    op.create_index("idx_series_items_series_id", "series_items", ["series_id"])
    op.create_table(
        "series_exclusions",
        sa.Column("gallery_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["gallery_id"], ["galleries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("gallery_id"),
    )


def downgrade() -> None:
    op.drop_table("series_exclusions")
    op.drop_index("idx_series_items_series_id", table_name="series_items")
    op.drop_table("series_items")
    op.drop_table("series")
