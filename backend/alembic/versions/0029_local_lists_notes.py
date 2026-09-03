"""Add local lists, local rating/note, and favorite notes.

Additive only: new tables and nullable columns. Does not drop or rewrite
existing data.
"""

import sqlalchemy as sa

from alembic import op

revision = "0029_local_lists_notes"
down_revision = "0028_download_task_title_jpn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("galleries", sa.Column("local_rating", sa.Integer(), nullable=True))
    op.add_column("galleries", sa.Column("local_note", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_galleries_local_rating",
        "galleries",
        "local_rating IS NULL OR (local_rating >= 1 AND local_rating <= 5)",
    )
    op.add_column("favorite_items", sa.Column("note", sa.Text(), nullable=True))
    op.create_table(
        "local_lists",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "local_list_items",
        sa.Column("list_id", sa.BigInteger(), nullable=False),
        sa.Column("gallery_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["list_id"], ["local_lists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["gallery_id"], ["galleries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("list_id", "gallery_id"),
    )
    op.create_index("idx_local_list_items_gallery_id", "local_list_items", ["gallery_id"])


def downgrade() -> None:
    op.drop_index("idx_local_list_items_gallery_id", table_name="local_list_items")
    op.drop_table("local_list_items")
    op.drop_table("local_lists")
    op.drop_column("favorite_items", "note")
    op.drop_constraint("ck_galleries_local_rating", "galleries", type_="check")
    op.drop_column("galleries", "local_note")
    op.drop_column("galleries", "local_rating")
