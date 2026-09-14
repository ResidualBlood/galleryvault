import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from galleryvault.config import get_settings


def _load_migration_0039():
    for candidate in [
        Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0039_audit_constraints.py",
        Path("/app/alembic/versions/0039_audit_constraints.py"),
    ]:
        if candidate.exists():
            spec = importlib.util.spec_from_file_location("migration_0039", candidate)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    msg = "0039_audit_constraints.py not found"
    raise FileNotFoundError(msg)


migration_0039 = _load_migration_0039()


@pytest.mark.asyncio
async def test_alembic_0039_deduplicate_and_constraints():
    db_url = get_settings().database_url
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database connection unavailable: {exc}")

    schema_name = f"test_mig_0039_{uuid.uuid4().hex[:8]}"

    setup_stmts = [
        f"CREATE SCHEMA {schema_name}",
        f"SET search_path TO {schema_name}, public",
        """
        CREATE TABLE galleries (
            id BIGSERIAL PRIMARY KEY,
            gid BIGINT,
            path_hash VARCHAR(64),
            local_rating DOUBLE PRECISION,
            local_note TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX idx_galleries_path_hash ON galleries (path_hash)",
        """
        CREATE TABLE tags (
            id BIGSERIAL PRIMARY KEY,
            name TEXT
        )
        """,
        """
        CREATE TABLE gallery_tags (
            gallery_id BIGINT,
            tag_id BIGINT,
            PRIMARY KEY (gallery_id, tag_id)
        )
        """,
        """
        CREATE TABLE local_lists (
            id BIGSERIAL PRIMARY KEY
        )
        """,
        """
        CREATE TABLE local_list_items (
            list_id BIGINT,
            gallery_id BIGINT,
            PRIMARY KEY (list_id, gallery_id)
        )
        """,
        """
        CREATE TABLE reading_progress (
            gallery_id BIGINT PRIMARY KEY,
            current_page INT,
            total_pages INT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE reading_history (
            id BIGSERIAL PRIMARY KEY,
            gallery_id BIGINT UNIQUE,
            current_page INT,
            total_pages INT,
            last_read_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE series (
            id BIGSERIAL PRIMARY KEY
        )
        """,
        """
        CREATE TABLE series_items (
            series_id BIGINT,
            gallery_id BIGINT PRIMARY KEY,
            source VARCHAR(16) DEFAULT 'auto'
        )
        """,
        """
        CREATE TABLE series_exclusions (
            gallery_id BIGINT PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE download_tasks (
            id BIGSERIAL PRIMARY KEY
        )
        """,
        """
        CREATE TABLE gallery_updates (
            id BIGSERIAL PRIMARY KEY,
            gallery_id BIGINT,
            old_gid BIGINT,
            new_gid BIGINT,
            new_token VARCHAR(64),
            title TEXT,
            favcat INT,
            status VARCHAR(16),
            download_task_id BIGINT,
            error_message TEXT,
            detected_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (gallery_id, new_gid)
        )
        """,
        """
        CREATE TABLE background_jobs (
            id BIGSERIAL PRIMARY KEY,
            job_type VARCHAR(32),
            gallery_id BIGINT,
            status VARCHAR(16),
            attempts INT DEFAULT 0,
            next_attempt_at TIMESTAMPTZ,
            lease_until TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (job_type, gallery_id)
        )
        """,
        """
        CREATE TABLE gallery_pages (
            id BIGSERIAL PRIMARY KEY,
            gallery_id BIGINT,
            page_index INT,
            member_name TEXT,
            media_type VARCHAR(16),
            manifest JSONB,
            UNIQUE (gallery_id, page_index)
        )
        """,
        # 脏数据插入：
        # 重复组 1: path_hash='dup_hash_1' (winner 无元数据，从 loser 101 继承)
        #   - 101: loser, gid=NULL, local_rating=4.5, local_note='note from 101'
        #   - 102: winner, gid=99901, local_rating=NULL, local_note=NULL
        #   - 103: loser, gid=NULL, local_rating=NULL, local_note=NULL
        "INSERT INTO galleries (id, gid, path_hash, local_rating, local_note) VALUES (101, NULL, 'dup_hash_1', 4.5, 'note from 101')",
        "INSERT INTO galleries (id, gid, path_hash, local_rating, local_note) VALUES (102, 99901, 'dup_hash_1', NULL, NULL)",
        "INSERT INTO galleries (id, gid, path_hash, local_rating, local_note) VALUES (103, NULL, 'dup_hash_1', NULL, NULL)",
        # 重复组 2: path_hash='dup_hash_2' (winner 已有元数据，不被 loser 301 覆盖)
        #   - 301: loser, gid=NULL, local_rating=2.0, local_note='loser note'
        #   - 302: winner, gid=99902, local_rating=5.0, local_note='winner note'
        "INSERT INTO galleries (id, gid, path_hash, local_rating, local_note) VALUES (301, NULL, 'dup_hash_2', 2.0, 'loser note')",
        "INSERT INTO galleries (id, gid, path_hash, local_rating, local_note) VALUES (302, 99902, 'dup_hash_2', 5.0, 'winner note')",
        # 正常组: path_hash='normal_hash'
        "INSERT INTO galleries (id, gid, path_hash, local_rating, local_note) VALUES (201, 88801, 'normal_hash', 5.0, 'clean note')",
        # 关联表数据：
        # 关联 loser 101 和 winner 102
        "INSERT INTO tags VALUES (1, 'tag1'), (2, 'tag2')",
        "INSERT INTO gallery_tags VALUES (101, 1), (102, 2)",
        "INSERT INTO local_lists VALUES (10)",
        "INSERT INTO local_list_items VALUES (10, 101)",
        "INSERT INTO reading_progress VALUES (101, 15, 30, NOW())",
        "INSERT INTO reading_progress VALUES (103, 20, 10, NOW() - INTERVAL '1 day')",
        "INSERT INTO reading_history (gallery_id, current_page, total_pages) VALUES (101, 15, 30)",
        "INSERT INTO reading_history (gallery_id, current_page, total_pages) VALUES (103, 8, 12)",
        "INSERT INTO series VALUES (20)",
        "INSERT INTO series_items VALUES (20, 101)",
        "INSERT INTO series_exclusions VALUES (101)",
        "INSERT INTO download_tasks VALUES (1)",
        "INSERT INTO gallery_updates (gallery_id, old_gid, new_gid, new_token, title, favcat, status, download_task_id) VALUES (101, 1, 2, 'tok', 'title', 0, 'pending', 1)",
        "INSERT INTO background_jobs (job_type, gallery_id, status) VALUES ('thumb', 101, 'pending'), ('thumb', 102, 'pending')",
        "INSERT INTO gallery_pages (gallery_id, page_index, member_name, media_type) VALUES (101, 0, 'p0.jpg', 'image/jpeg')",
    ]

    async with engine.connect() as conn:
        try:
            for s in setup_stmts:
                await conn.execute(text(s))
            await conn.commit()

            # 运行 0039 upgrade
            def run_upgrade(sync_conn):
                sync_conn.execute(text(f"SET search_path TO {schema_name}, public"))
                ctx = MigrationContext.configure(sync_conn)
                with Operations.context(ctx):
                    migration_0039.upgrade()

            await conn.run_sync(run_upgrade)
            await conn.commit()
            await conn.execute(text(f"SET search_path TO {schema_name}, public"))

            # 验证去重与 winner 保留
            galleries = (
                await conn.execute(
                    text("SELECT id, gid, path_hash, local_rating, local_note FROM galleries ORDER BY id")
                )
            ).fetchall()
            assert len(galleries) == 3

            winner_row_1 = galleries[0]
            assert winner_row_1[0] == 102
            assert winner_row_1[1] == 99901
            assert winner_row_1[2] == "dup_hash_1"
            assert winner_row_1[3] == 4.5
            assert winner_row_1[4] == "note from 101"

            clean_row = galleries[1]
            assert clean_row[0] == 201
            assert clean_row[1] == 88801
            assert clean_row[2] == "normal_hash"

            winner_row_2 = galleries[2]
            assert winner_row_2[0] == 302
            assert winner_row_2[1] == 99902
            assert winner_row_2[2] == "dup_hash_2"
            assert winner_row_2[3] == 5.0
            assert winner_row_2[4] == "winner note"

            # 验证 tags 迁移合并
            tags = (
                await conn.execute(
                    text("SELECT gallery_id, tag_id FROM gallery_tags ORDER BY tag_id")
                )
            ).fetchall()
            assert tags == [(102, 1), (102, 2)]

            # 验证 list 关联迁移
            lists = (
                await conn.execute(
                    text("SELECT list_id, gallery_id FROM local_list_items")
                )
            ).fetchall()
            assert lists == [(10, 102)]

            # 验证 reading_progress 迁移：多 loser 取同一行（current_page 最大的 103）
            progress = (
                await conn.execute(
                    text("SELECT gallery_id, current_page, total_pages FROM reading_progress")
                )
            ).fetchall()
            assert progress == [(102, 20, 10)]

            # 验证 reading_history 迁移：取 current_page 较大的 101，不拼 103 的 total
            history = (
                await conn.execute(
                    text("SELECT gallery_id, current_page, total_pages FROM reading_history")
                )
            ).fetchall()
            assert history == [(102, 15, 30)]

            # 验证 series_items 迁移
            series_items = (
                await conn.execute(
                    text("SELECT series_id, gallery_id FROM series_items")
                )
            ).fetchall()
            assert series_items == [(20, 102)]

            # 验证 UNIQUE 索引建立并生效（冲突插入必须抛出异常）
            with pytest.raises(Exception):  # noqa: B017
                async with conn.begin_nested():
                    await conn.execute(
                        text("INSERT INTO galleries (path_hash) VALUES ('dup_hash_1')")
                    )

            # 验证幂等性：无重复数据时重复执行清洗逻辑不报错
            await conn.run_sync(run_upgrade)
            await conn.commit()

        finally:
            try:
                await conn.rollback()
            except Exception:  # noqa: BLE001, S110
                pass
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            await conn.commit()
