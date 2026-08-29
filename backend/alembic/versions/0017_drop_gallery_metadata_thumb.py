"""Drop gallery_metadata.thumb (rolled back).

Covers are now downloaded to disk during the favorites metadata sync (from the
fresh gdata thumb URL) instead of persisting the thumb URL — matching the
check-design where a folder check warms covers, tags and sizes together.
"""

import sqlalchemy as sa

from alembic import op

revision = "0017_drop_gallery_metadata_thumb"
down_revision = "0016_gallery_metadata_thumb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("gallery_metadata", "thumb")


def downgrade() -> None:
    op.add_column("gallery_metadata", sa.Column("thumb", sa.Text(), nullable=True))
