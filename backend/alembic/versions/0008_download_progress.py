"""Track download progress (current/total pages) for the UI progress bar."""

import sqlalchemy as sa

from alembic import op

revision = "0008_download_progress"
down_revision = "0007_tags_synced_at_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("download_tasks", sa.Column("current_page", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("download_tasks", sa.Column("total_pages", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("download_tasks", "total_pages")
    op.drop_column("download_tasks", "current_page")