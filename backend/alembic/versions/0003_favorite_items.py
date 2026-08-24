"""Persist favorite gallery observations."""

import sqlalchemy as sa

from alembic import op

revision = "0003_favorite_items"
down_revision = "0002_download_monitor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "favorite_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("favcat", sa.Integer(), nullable=False),
        sa.Column("gid", sa.BigInteger(), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("favcat", "gid"),
    )
    op.create_index("idx_favorite_items_gid", "favorite_items", ["gid"])


def downgrade() -> None:
    op.drop_index("idx_favorite_items_gid", table_name="favorite_items")
    op.drop_table("favorite_items")
