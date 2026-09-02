"""Add active download protection and favorites polling interval."""

import sqlalchemy as sa

from alembic import op

revision = "0002_download_monitor"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "favorites_monitor",
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="43200"),
    )
    op.create_index(
        "idx_download_tasks_active_gid",
        "download_tasks",
        ["gid"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'downloading')"),
    )
    op.create_check_constraint(
        "ck_download_task_status",
        "download_tasks",
        "status IN ('pending', 'downloading', 'success', 'failed', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_download_task_max_retries", "download_tasks", "max_retries BETWEEN 0 AND 3"
    )


def downgrade() -> None:
    op.drop_constraint("ck_download_task_max_retries", "download_tasks", type_="check")
    op.drop_constraint("ck_download_task_status", "download_tasks", type_="check")
    op.drop_index("idx_download_tasks_active_gid", table_name="download_tasks")
    op.drop_column("favorites_monitor", "poll_interval_seconds")
