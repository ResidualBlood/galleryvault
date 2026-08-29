"""Add the persistent background-jobs queue.

Thumbnail generation and tag-sync previously used in-memory ``asyncio.Queue``
workers, so queued work was lost on restart.  The new ``background_jobs`` table
(one row per ``(job_type, gallery_id)``) survives restarts and lets a future
multi-process deployment claim jobs safely via ``FOR UPDATE SKIP LOCKED``.
Completed rows are deleted; ``lease_until`` reopens rows whose claiming worker
died mid-job.
"""

import sqlalchemy as sa

from alembic import op

revision = "0021_background_jobs"
down_revision = "0020_download_retry_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("gallery_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_type", "gallery_id"),
    )
    op.create_index(
        "idx_background_jobs_claim",
        "background_jobs",
        ["job_type", "status", "next_attempt_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("idx_background_jobs_claim", table_name="background_jobs")
    op.drop_table("background_jobs")
