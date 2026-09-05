"""Add archive_status and archive_error to download_tasks.

Additive only: records cold storage archive status (null|pending|ok|fail) and error
for completed download tasks without impacting download success state.
"""

import sqlalchemy as sa

from alembic import op

revision = "0034_download_archive_status"
down_revision = "0033_series_cloud_exclusions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "download_tasks",
        sa.Column("archive_status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "download_tasks",
        sa.Column("archive_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("download_tasks", "archive_error")
    op.drop_column("download_tasks", "archive_status")
