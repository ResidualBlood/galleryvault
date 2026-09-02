"""User-marked duplicate groups to skip in the favorite duplicate scan.

Some galleries share an identical title but are different works; letting the
user mark such a group as ignored keeps the manager free of false positives.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014_duplicate_ignores"
down_revision = "0013_gallery_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "favorite_duplicate_ignores",
        sa.Column("key", sa.String(512), primary_key=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("gids", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("favorite_duplicate_ignores")
