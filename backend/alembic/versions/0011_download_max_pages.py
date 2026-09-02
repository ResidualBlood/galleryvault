"""Add download_tasks.max_pages so partial/sample downloads survive the worker.

The API accepted max_pages but the persistent download worker rebuilt the task
from the DB row without it, silently downloading every page.
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_download_max_pages"
down_revision = "0010_category_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "download_tasks",
        sa.Column("max_pages", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("download_tasks", "max_pages")