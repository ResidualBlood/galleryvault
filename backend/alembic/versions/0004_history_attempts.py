"""Persist reading history and download attempt diagnostics."""

import sqlalchemy as sa

from alembic import op

revision = "0004_history_attempts"
down_revision = "0003_favorite_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reading_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "gallery_id",
            sa.BigInteger(),
            sa.ForeignKey("galleries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_page", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_pages", sa.Integer()),
        sa.Column(
            "last_read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_reading_history_last_read", "reading_history", ["last_read_at"])
    op.create_table(
        "download_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "task_id",
            sa.BigInteger(),
            sa.ForeignKey("download_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_download_attempts_task", "download_attempts", ["task_id"])


def downgrade() -> None:
    op.drop_index("idx_download_attempts_task", table_name="download_attempts")
    op.drop_table("download_attempts")
    op.drop_index("idx_reading_history_last_read", table_name="reading_history")
    op.drop_table("reading_history")
