"""Add title_jpn to download_tasks.

Additive only: stores the Japanese title alongside ``title`` so the downloads
list can follow ``title_display`` (english/japanese) without a second ExHentai
fetch.
"""

import sqlalchemy as sa

from alembic import op

revision = "0028_download_task_title_jpn"
down_revision = "0027_gallery_trash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("download_tasks", sa.Column("title_jpn", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("download_tasks", "title_jpn")
