"""Merge misc/other and move orphan galleries to deleted.

- Galleries in the generic 'other' bucket with ExHentai coordinates that have
  been category-refreshed move to 'misc' (misc and other are the same bucket).
- Galleries with no ExHentai coordinates (cannot be classified or synced) and
  those already marked 'deleted' are grouped under 'deleted'.
"""

from alembic import op

revision = "0010_category_merge"
down_revision = "0009_category_refresh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Coordinates exist -> real bucket is misc (or was corrected by backfill).
    # gid is a bigint so only a NULL check applies; token is text.
    op.execute(
        "UPDATE galleries SET category='misc' WHERE category='other' "
        "AND gid IS NOT NULL AND token IS NOT NULL AND token <> ''"
    )
    # No coordinates -> cannot classify/sync, treat as deleted/orphan.
    op.execute(
        "UPDATE galleries SET category='deleted' WHERE category='other' "
        "AND (gid IS NULL OR token IS NULL OR token = '')"
    )


def downgrade() -> None:
    # Non-reversible data merge; leave rows as-is.
    pass