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
    # 0. Deduplicate duplicate path_hash entries in galleries before creating unique index
    statements = [
        """
        CREATE TEMP TABLE _dup_gallery_mapping AS
        WITH ranked AS (
            SELECT
                id,
                path_hash,
                ROW_NUMBER() OVER (
                    PARTITION BY path_hash
                    ORDER BY
                        (CASE WHEN gid IS NOT NULL THEN 1 ELSE 0 END) DESC,
                        updated_at DESC,
                        id DESC
                ) AS rn,
                FIRST_VALUE(id) OVER (
                    PARTITION BY path_hash
                    ORDER BY
                        (CASE WHEN gid IS NOT NULL THEN 1 ELSE 0 END) DESC,
                        updated_at DESC,
                        id DESC
                ) AS winner_id
            FROM galleries
            WHERE path_hash IN (
                SELECT path_hash
                FROM galleries
                GROUP BY path_hash
                HAVING COUNT(*) > 1
            )
        )
        SELECT
            id AS loser_id,
            winner_id,
            path_hash
        FROM ranked
        WHERE rn > 1
        """,
        """
        WITH loser_meta AS (
            SELECT
                m.winner_id,
                (ARRAY_AGG(l.local_rating ORDER BY l.updated_at DESC, l.id DESC)
                 FILTER (WHERE l.local_rating IS NOT NULL))[1] AS local_rating,
                (ARRAY_AGG(l.local_note ORDER BY l.updated_at DESC, l.id DESC)
                 FILTER (WHERE l.local_note IS NOT NULL AND l.local_note <> ''))[1] AS local_note
            FROM _dup_gallery_mapping m
            JOIN galleries l ON l.id = m.loser_id
            GROUP BY m.winner_id
        )
        UPDATE galleries g
        SET local_rating = COALESCE(g.local_rating, lm.local_rating),
            local_note = CASE
                WHEN g.local_note IS NULL OR g.local_note = '' THEN lm.local_note
                ELSE g.local_note
            END
        FROM loser_meta lm
        WHERE g.id = lm.winner_id
        """,
        """
        INSERT INTO gallery_tags (gallery_id, tag_id)
        SELECT m.winner_id, gt.tag_id
        FROM gallery_tags gt
        JOIN _dup_gallery_mapping m ON gt.gallery_id = m.loser_id
        ON CONFLICT DO NOTHING
        """,
        "DELETE FROM gallery_tags gt USING _dup_gallery_mapping m WHERE gt.gallery_id = m.loser_id",
        """
        INSERT INTO local_list_items (list_id, gallery_id)
        SELECT lli.list_id, m.winner_id
        FROM local_list_items lli
        JOIN _dup_gallery_mapping m ON lli.gallery_id = m.loser_id
        ON CONFLICT DO NOTHING
        """,
        "DELETE FROM local_list_items lli USING _dup_gallery_mapping m WHERE lli.gallery_id = m.loser_id",
        """
        INSERT INTO reading_progress (gallery_id, current_page, total_pages, updated_at)
        SELECT m.winner_id, rp.current_page, rp.total_pages, rp.updated_at
        FROM reading_progress rp
        JOIN _dup_gallery_mapping m ON rp.gallery_id = m.loser_id
        ON CONFLICT (gallery_id) DO UPDATE SET
            current_page = GREATEST(reading_progress.current_page, EXCLUDED.current_page),
            updated_at = GREATEST(reading_progress.updated_at, EXCLUDED.updated_at)
        """,
        "DELETE FROM reading_progress rp USING _dup_gallery_mapping m WHERE rp.gallery_id = m.loser_id",
        """
        INSERT INTO reading_history (gallery_id, current_page, total_pages, last_read_at)
        SELECT m.winner_id, rh.current_page, rh.total_pages, rh.last_read_at
        FROM reading_history rh
        JOIN _dup_gallery_mapping m ON rh.gallery_id = m.loser_id
        ON CONFLICT (gallery_id) DO UPDATE SET
            current_page = GREATEST(reading_history.current_page, EXCLUDED.current_page),
            last_read_at = GREATEST(reading_history.last_read_at, EXCLUDED.last_read_at)
        """,
        "DELETE FROM reading_history rh USING _dup_gallery_mapping m WHERE rh.gallery_id = m.loser_id",
        """
        INSERT INTO series_items (gallery_id, series_id, source)
        SELECT m.winner_id, si.series_id, si.source
        FROM series_items si
        JOIN _dup_gallery_mapping m ON si.gallery_id = m.loser_id
        ON CONFLICT (gallery_id) DO NOTHING
        """,
        "DELETE FROM series_items si USING _dup_gallery_mapping m WHERE si.gallery_id = m.loser_id",
        """
        INSERT INTO series_exclusions (gallery_id, created_at)
        SELECT m.winner_id, se.created_at
        FROM series_exclusions se
        JOIN _dup_gallery_mapping m ON se.gallery_id = m.loser_id
        ON CONFLICT (gallery_id) DO NOTHING
        """,
        "DELETE FROM series_exclusions se USING _dup_gallery_mapping m WHERE se.gallery_id = m.loser_id",
        """
        INSERT INTO gallery_updates (
            gallery_id, old_gid, new_gid, new_token, title, favcat,
            status, download_task_id, error_message, detected_at, updated_at
        )
        SELECT
            m.winner_id, gu.old_gid, gu.new_gid, gu.new_token, gu.title, gu.favcat,
            gu.status, gu.download_task_id, gu.error_message, gu.detected_at, gu.updated_at
        FROM gallery_updates gu
        JOIN _dup_gallery_mapping m ON gu.gallery_id = m.loser_id
        ON CONFLICT (gallery_id, new_gid) DO NOTHING
        """,
        "DELETE FROM gallery_updates gu USING _dup_gallery_mapping m WHERE gu.gallery_id = m.loser_id",
        """
        INSERT INTO background_jobs (
            job_type, gallery_id, status, attempts, next_attempt_at,
            lease_until, created_at, updated_at
        )
        SELECT
            bj.job_type, m.winner_id, bj.status, bj.attempts, bj.next_attempt_at,
            bj.lease_until, bj.created_at, bj.updated_at
        FROM background_jobs bj
        JOIN _dup_gallery_mapping m ON bj.gallery_id = m.loser_id
        ON CONFLICT (job_type, gallery_id) DO NOTHING
        """,
        "DELETE FROM background_jobs bj USING _dup_gallery_mapping m WHERE bj.gallery_id = m.loser_id",
        """
        INSERT INTO gallery_pages (gallery_id, page_index, member_name, media_type, manifest)
        SELECT m.winner_id, gp.page_index, gp.member_name, gp.media_type, gp.manifest
        FROM gallery_pages gp
        JOIN _dup_gallery_mapping m ON gp.gallery_id = m.loser_id
        ON CONFLICT (gallery_id, page_index) DO NOTHING
        """,
        "DELETE FROM gallery_pages gp USING _dup_gallery_mapping m WHERE gp.gallery_id = m.loser_id",
        "DELETE FROM galleries g USING _dup_gallery_mapping m WHERE g.id = m.loser_id",
        "DROP TABLE IF EXISTS _dup_gallery_mapping",
        """
        UPDATE gallery_updates
        SET download_task_id = NULL
        WHERE download_task_id IS NOT NULL
          AND download_task_id NOT IN (SELECT id FROM download_tasks)
        """,
        "DELETE FROM background_jobs WHERE gallery_id NOT IN (SELECT id FROM galleries)",
        "DROP INDEX IF EXISTS idx_galleries_path_hash",
        "ALTER TABLE gallery_updates DROP CONSTRAINT IF EXISTS fk_gallery_updates_download_task_id",
        "ALTER TABLE background_jobs DROP CONSTRAINT IF EXISTS fk_background_jobs_gallery_id",
    ]
    for stmt in statements:
        op.execute(stmt)

    # 1. Update idx_galleries_path_hash to UNIQUE
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
