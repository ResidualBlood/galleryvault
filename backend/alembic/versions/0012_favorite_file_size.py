"""Add favorite_items.file_size for exact cloud-size estimates.

The favorite monitor can fetch each missing gallery's size from ExHentai and
store it here, so the Favorites page can report an exact cloud size instead of
an average-based estimate.
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_favorite_file_size"
down_revision = "0011_download_max_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "favorite_items",
        sa.Column("file_size", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("favorite_items", "file_size")