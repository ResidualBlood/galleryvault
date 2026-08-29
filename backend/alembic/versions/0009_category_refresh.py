"""Add category_refreshed_at for the one-time 大分类 backfill."""

import sqlalchemy as sa

from alembic import op

revision = "0009_category_refresh"
down_revision = "0008_download_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "galleries", sa.Column("category_refreshed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("galleries", "category_refreshed_at")