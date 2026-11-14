"""Track download ingest state so ``success`` means "already in the library".

A finished download is no longer reported as ``success`` before the gallery is
imported: ``status`` stays ``downloading`` while ``ingest_status='pending'`` and
``ingest_payload`` carries the in-memory result snapshot for the DB-driven
ingest pump. The pump writes ``success``/``done`` only after the library insert,
or ``failed``/``failed`` when the import fails.

Historical ``success`` rows whose gid is already in ``galleries`` are backfilled
to ``done``. Rows whose gid is not in ``galleries`` keep ``NULL``: the user may
have deleted the gallery afterwards and no automatic retry is possible.

Revision ID: 0043_download_ingest_state
Revises: 0042_online_reading_progress
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0043_download_ingest_state"
down_revision = "0042_online_reading_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "download_tasks",
        sa.Column("ingest_status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "download_tasks",
        sa.Column("ingest_payload", postgresql.JSONB(), nullable=True),
    )
    op.create_check_constraint(
        "ck_download_task_ingest_status",
        "download_tasks",
        "ingest_status IS NULL OR ingest_status IN ('pending', 'done', 'failed')",
    )
    op.create_index(
        "idx_download_tasks_ingest_pending",
        "download_tasks",
        ["id"],
        postgresql_where=sa.text("ingest_status = 'pending'"),
    )
    op.execute(
        sa.text(
            "UPDATE download_tasks AS dt SET ingest_status = 'done' "
            "WHERE dt.status = 'success' AND dt.ingest_status IS NULL "
            "AND EXISTS (SELECT 1 FROM galleries g WHERE g.gid = dt.gid)"
        )
    )


def downgrade() -> None:
    op.drop_index("idx_download_tasks_ingest_pending", table_name="download_tasks")
    op.drop_constraint(
        "ck_download_task_ingest_status", "download_tasks", type_="check"
    )
    op.drop_column("download_tasks", "ingest_payload")
    op.drop_column("download_tasks", "ingest_status")
