"""Store the cover thumb URL captured from the favorites listing.

A favorites check reads the listing HTML which embeds each gallery's cover
thumbnail URL.  Persisting it lets the metadata sync warm cover files on disk
without a separate gdata round-trip, and lets the lazy browsing endpoint
re-download a missing cover for cached items.
"""

import sqlalchemy as sa

from alembic import op

revision = "0018_favorite_items_thumb"
down_revision = "0017_drop_gallery_metadata_thumb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("favorite_items", sa.Column("thumb", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("favorite_items", "thumb")
