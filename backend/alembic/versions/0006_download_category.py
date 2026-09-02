"""Store category discovered during a download."""

import sqlalchemy as sa

from alembic import op

revision = "0006_download_category"
down_revision = "0005_fav_logs_hist_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("download_tasks", sa.Column("category", sa.String(32)))


def downgrade() -> None:
    op.drop_column("download_tasks", "category")
