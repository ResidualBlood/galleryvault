"""Store the ExHentai cover thumb URL in gallery_metadata.

Covers for cloud-only favorite items are downloaded lazily from the gdata
``thumb`` URL.  Previously the thumb was never persisted, so once an item was
cached the URL was dropped (``_favorites_metadata`` returned ``thumb: ""``) and
a missing disk cover could never be re-fetched.
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_gallery_metadata_thumb"
down_revision = "0015_galleries_title_trgm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gallery_metadata", sa.Column("thumb", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("gallery_metadata", "thumb")
