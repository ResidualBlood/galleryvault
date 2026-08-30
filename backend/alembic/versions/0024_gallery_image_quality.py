"""Add on-disk image quality to galleries.

Tracks whether the local copy of a gallery is original or resampled so the
detail page can show a quality badge and offer "download original" actions
only when the gallery is not already original.  Additive only: nullable
column, ``NULL`` means unknown (conservative: the upgrade buttons stay
visible).
"""

import sqlalchemy as sa

from alembic import op

revision = "0024_gallery_image_quality"
down_revision = "0023_download_task_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "galleries",
        sa.Column("image_quality", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("galleries", "image_quality")
