"""Add idx_download_tasks_status_id index.

Additive only: compound index on download_tasks (status, id DESC) to support
efficient status filtering and reversed id pagination.
"""

import sqlalchemy as sa

from alembic import op

revision = "0036_download_tasks_status_id"
down_revision = "0035_gallery_storage_path_like"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_download_tasks_status_id",
        "download_tasks",
        ["status", sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_download_tasks_status_id", table_name="download_tasks")
