"""Audit schema constraints.

1. Ensure idx_galleries_path_hash is a UNIQUE index on galleries(path_hash).
2. Add foreign key fk_gallery_updates_download_task_id from gallery_updates.download_task_id
   to download_tasks.id with ondelete="SET NULL".
3. Add foreign key fk_background_jobs_gallery_id from background_jobs.gallery_id
   to galleries.id with ondelete="CASCADE".
"""

from alembic import op

revision = "0039_audit_constraints"
down_revision = "0038_gallery_metadata_thumb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Update idx_galleries_path_hash to UNIQUE
    op.drop_index("idx_galleries_path_hash", table_name="galleries")
    op.create_index("idx_galleries_path_hash", "galleries", ["path_hash"], unique=True)

    # 2. Add FK for gallery_updates.download_task_id -> download_tasks.id (SET NULL)
    op.create_foreign_key(
        "fk_gallery_updates_download_task_id",
        "gallery_updates",
        "download_tasks",
        ["download_task_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Add FK for background_jobs.gallery_id -> galleries.id (CASCADE)
    op.create_foreign_key(
        "fk_background_jobs_gallery_id",
        "background_jobs",
        "galleries",
        ["gallery_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # 3. Drop FK for background_jobs.gallery_id
    op.drop_constraint("fk_background_jobs_gallery_id", "background_jobs", type_="foreignkey")

    # 2. Drop FK for gallery_updates.download_task_id
    op.drop_constraint("fk_gallery_updates_download_task_id", "gallery_updates", type_="foreignkey")

    # 1. Restore non-unique idx_galleries_path_hash
    op.drop_index("idx_galleries_path_hash", table_name="galleries")
    op.create_index("idx_galleries_path_hash", "galleries", ["path_hash"], unique=False)
