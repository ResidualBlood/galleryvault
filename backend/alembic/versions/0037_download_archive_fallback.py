"""Add archive_fallback column to download_tasks.

Additive only: tracks whether an archive task fell back to page-by-page download,
avoiding synchronous disk inspection during download list pagination.
"""

import sqlalchemy as sa

from alembic import op

revision = "0037_download_archive_fallback"
down_revision = "0036_download_tasks_status_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "download_tasks",
        sa.Column(
            "archive_fallback",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("download_tasks", "archive_fallback")
