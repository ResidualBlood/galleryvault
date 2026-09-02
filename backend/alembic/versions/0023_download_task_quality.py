"""Add archive-download quality to download_tasks.

The ExHentai archive download channel stores the requested quality tier
(``resample`` / ``original``) per task so the executor can pick the right
archive form without re-deriving it from global settings.  Additive only:
``quality`` is nullable and ``mode`` is widened to fit ``favorite_archive``.
"""

import sqlalchemy as sa

from alembic import op

revision = "0023_download_task_quality"
down_revision = "0022_gallery_updates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "download_tasks",
        sa.Column("quality", sa.String(length=16), nullable=True),
    )
    op.alter_column(
        "download_tasks",
        "mode",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "download_tasks",
        "mode",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=True,
    )
    op.drop_column("download_tasks", "quality")
