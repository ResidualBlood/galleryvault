"""Store duplicate-copy groups found by library scans.

A scan may find the same gallery (same gid) under several scan roots; each
detected group is persisted here so the UI can list every physical copy and
let the user pick which one to keep.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0019_duplicate_records"
down_revision = "0018_favorite_items_thumb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "duplicate_records",
        sa.Column("gid", sa.BigInteger(), primary_key=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "policy",
            sa.String(24),
            nullable=False,
            server_default="keep_first",
        ),
        sa.Column("winner_path", sa.Text(), nullable=True),
        sa.Column(
            "copies",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("duplicate_records")
