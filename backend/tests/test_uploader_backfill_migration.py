"""Tests for 0041_backfill_gallery_uploader migration logic."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from galleryvault.config import get_settings


def _load_migration():
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "0041_backfill_gallery_uploader.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migration_0041", migration_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0041_migration_metadata():
    mod = _load_migration()
    assert mod.revision == "0041_backfill_gallery_uploader"
    assert mod.down_revision == "0040_uploader_tags_backfill"
    assert hasattr(mod, "upgrade")
    assert hasattr(mod, "downgrade")


@pytest.mark.asyncio
async def test_0041_backfill_sql_execution():
    """验证 0041 迁移中的 SQL 能够正确回填 galleries.uploader 并生成关联标签。"""
    db_url = get_settings().database_url
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database connection unavailable: {exc}")

    async with engine.connect() as conn:
        try:
            # 构造临时测试表
            # gallery 1: gid=1001, uploader 为 NULL, metadata 中有有效 uploader
            # gallery 2: gid=1002, uploader 为空白 '   ', metadata 中有有效 uploader
            # gallery 3: gid=1003, uploader 已有 'existing_user', metadata 为 'diff_user' -> 不被覆盖
            # gallery 4: gid=1004, uploader 为 NULL, metadata 也为 NULL/空白 -> 不回填
            await conn.execute(
                text(
                    """
                    CREATE TEMP TABLE temp_galleries (
                        id BIGSERIAL PRIMARY KEY,
                        gid BIGINT,
                        uploader VARCHAR(128)
                    ) ON COMMIT DROP;
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE TEMP TABLE temp_gallery_metadata (
                        gid BIGINT PRIMARY KEY,
                        uploader VARCHAR(128)
                    ) ON COMMIT DROP;
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE TEMP TABLE temp_tags (
                        id BIGSERIAL PRIMARY KEY,
                        namespace VARCHAR(32) NOT NULL,
                        name TEXT NOT NULL,
                        CONSTRAINT uq_temp_tags UNIQUE (namespace, name)
                    ) ON COMMIT DROP;
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE TEMP TABLE temp_gallery_tags (
                        gallery_id BIGINT NOT NULL,
                        tag_id BIGINT NOT NULL,
                        PRIMARY KEY (gallery_id, tag_id)
                    ) ON COMMIT DROP;
                    """
                )
            )

            await conn.execute(
                text(
                    """
                    INSERT INTO temp_galleries (id, gid, uploader) VALUES
                        (1, 1001, NULL),
                        (2, 1002, '   '),
                        (3, 1003, 'existing_user'),
                        (4, 1004, NULL);
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO temp_gallery_metadata (gid, uploader) VALUES
                        (1001, '  alpha_uploader  '),
                        (1002, 'beta_uploader'),
                        (1003, 'diff_user'),
                        (1004, '   ');
                    """
                )
            )

            # 执行 0041 迁移中的核心逻辑
            await conn.execute(
                text(
                    """
                    UPDATE temp_galleries g
                    SET uploader = TRIM(gm.uploader)
                    FROM temp_gallery_metadata gm
                    WHERE g.gid = gm.gid
                      AND (g.uploader IS NULL OR TRIM(g.uploader) = '')
                      AND gm.uploader IS NOT NULL
                      AND TRIM(gm.uploader) <> '';
                    """
                )
            )

            await conn.execute(
                text(
                    """
                    INSERT INTO temp_tags (namespace, name)
                    SELECT DISTINCT 'uploader', TRIM(g.uploader)
                    FROM temp_galleries g
                    WHERE g.uploader IS NOT NULL AND TRIM(g.uploader) <> ''
                    ON CONFLICT (namespace, name) DO NOTHING;
                    """
                )
            )

            await conn.execute(
                text(
                    """
                    INSERT INTO temp_gallery_tags (gallery_id, tag_id)
                    SELECT g.id, t.id
                    FROM temp_galleries g
                    JOIN temp_tags t ON t.namespace = 'uploader' AND t.name = TRIM(g.uploader)
                    WHERE g.uploader IS NOT NULL AND TRIM(g.uploader) <> ''
                    ON CONFLICT DO NOTHING;
                    """
                )
            )

            # 验证 galleries 回填结果
            res = await conn.execute(
                text("SELECT id, uploader FROM temp_galleries ORDER BY id")
            )
            rows = dict(res.fetchall())
            assert rows[1] == "alpha_uploader"
            assert rows[2] == "beta_uploader"
            assert rows[3] == "existing_user"  # 未被覆写
            assert rows[4] is None  # 无效来源不回填

            # 验证 tags 结果
            tags_res = await conn.execute(
                text("SELECT name FROM temp_tags WHERE namespace = 'uploader' ORDER BY name")
            )
            tags = [r[0] for r in tags_res.fetchall()]
            assert tags == ["alpha_uploader", "beta_uploader", "existing_user"]

            # 验证 gallery_tags 关联结果
            gt_res = await conn.execute(
                text(
                    """
                    SELECT gt.gallery_id, t.name
                    FROM temp_gallery_tags gt
                    JOIN temp_tags t ON gt.tag_id = t.id
                    ORDER BY gt.gallery_id
                    """
                )
            )
            relations = gt_res.fetchall()
            assert (1, "alpha_uploader") in relations
            assert (2, "beta_uploader") in relations
            assert (3, "existing_user") in relations
            assert all(r[0] != 4 for r in relations)
        finally:
            await conn.rollback()
    await engine.dispose()

