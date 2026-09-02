"""Add download task retry-at scheduling and relax the retry cap.

Failed downloads now re-enter the pending queue with an exponential backoff
instead of exhausting only three attempts and staying failed. The ``retry_at``
column holds the earliest time the task may be claimed again, and the
``max_retries`` cap is widened from 3 to 10 so long galleries self-heal.
"""

import sqlalchemy as sa

from alembic import op

revision = "0020_download_retry_at"
down_revision = "0019_duplicate_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "download_tasks",
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "ALTER TABLE download_tasks DROP CONSTRAINT ck_download_task_max_retries"
    )
    op.create_check_constraint(
        "ck_download_task_max_retries",
        "download_tasks",
        "max_retries BETWEEN 0 AND 10",
    )
    op.execute(
        "UPDATE download_tasks SET max_retries = 10 WHERE max_retries = 3"
    )


def downgrade() -> None:
    op.drop_column("download_tasks", "retry_at")
    op.execute(
        "ALTER TABLE download_tasks DROP CONSTRAINT ck_download_task_max_retries"
    )
    op.create_check_constraint(
        "ck_download_task_max_retries",
        "download_tasks",
        "max_retries BETWEEN 0 AND 3",
    )
