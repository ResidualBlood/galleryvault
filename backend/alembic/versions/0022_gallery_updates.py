"""Add the gallery-updates tracking table.

ExHentai re-uploads move a gallery to a new gid and the favorites entry
follows it; the older local copy is detected by matching its normalized title
against the favorites list.  ``gallery_updates`` records one pending update per
local gallery; the row cascade-deletes with its gallery so a finished update
disappears from the page automatically.
"""

import sqlalchemy as sa

from alembic import op

revision = "0022_gallery_updates"
down_revision = "0021_background_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gallery_updates",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("gallery_id", sa.BigInteger(), nullable=False),
        sa.Column("old_gid", sa.BigInteger(), nullable=False),
        sa.Column("new_gid", sa.BigInteger(), nullable=False),
        sa.Column("new_token", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("favcat", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("download_task_id", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "detected_at",
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
        sa.ForeignKeyConstraint(["gallery_id"], ["galleries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gallery_id", "new_gid"),
    )
    op.create_index("idx_gallery_updates_status", "gallery_updates", ["status", "id"])


def downgrade() -> None:
    op.drop_index("idx_gallery_updates_status", table_name="gallery_updates")
    op.drop_table("gallery_updates")
