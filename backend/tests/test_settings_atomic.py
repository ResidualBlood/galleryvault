"""T6.3: user_settings writes are atomic (INSERT ... ON CONFLICT jsonb merge).

DB-free guardrails: the compiled upsert shape and an AST guard that production
code never rewrites the whole ``app_config.user_settings`` blob.  The real
concurrency behaviour is covered by ``test_settings_atomic_pg.py``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from galleryvault.db.repositories.settings import SettingsRepository, patch_settings

PROJECT = Path(__file__).resolve().parents[1] / "galleryvault"
# Files that used to read the whole blob and write it back.  Every one of them
# must now submit only its own keys through ``patch_settings``.
PATCH_SITES = {
    "app/routers/settings.py",
    "app/routers/tasks.py",
    "app/lifespan.py",
    "services/tgbot/handlers/queue.py",
    "services/download_worker.py",
}


def _compiled(changes: dict, remove: tuple[str, ...] = ()) -> str:
    stmt = SettingsRepository.patch_statement(changes, remove)
    sql = stmt.compile(dialect=postgresql.dialect())
    return " ".join(str(sql).split())


def test_patch_compiles_to_jsonb_merge_upsert() -> None:
    sql = _compiled({"global_paused": True})
    assert "INSERT INTO app_config" in sql
    assert "ON CONFLICT (key) DO UPDATE" in sql
    assert "value = (app_config.value || excluded.value)" in sql


def test_patch_compiles_remove_as_jsonb_key_subtraction() -> None:
    # jsonb ``#-`` takes a *path*: ``{a,b}`` deletes nested a.b, not top-level
    # a and b.  Key removal must use ``jsonb - text[]`` instead.
    sql = _compiled({"saved_searches": []}, remove=("saved_searches",))
    assert "#-" not in sql
    assert "(app_config.value || excluded.value) - " in sql
    assert "TEXT[]" in sql


def test_patch_removes_every_named_key_with_one_subtraction() -> None:
    sql = _compiled({"keep": 1}, remove=("a", "b"))
    assert "#-" not in sql
    # One text[] operand, not a nested path of two elements.
    assert sql.count("TEXT[]") == 1
    assert "(app_config.value || excluded.value) - " in sql


def test_patch_has_no_remove_clause_when_remove_is_empty() -> None:
    assert "#-" not in _compiled({"title_display": "english"})


def test_no_whole_blob_settings_save_in_production_code() -> None:
    offenders: list[str] = []
    for path in sorted(PROJECT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "save"
                and "SettingsRepository" in ast.unparse(node.func.value)
            ):
                offenders.append(f"{path.relative_to(PROJECT)}:{node.lineno}")
    assert offenders == []


def test_every_settings_write_site_uses_the_patch_helper() -> None:
    seen: set[str] = set()
    for path in PROJECT.rglob("*.py"):
        if "patch_settings(" in path.read_text(encoding="utf-8"):
            seen.add(str(path.relative_to(PROJECT)))
    assert PATCH_SITES <= seen


def test_repository_exposes_atomic_helpers_only() -> None:
    assert inspect.iscoroutinefunction(SettingsRepository.patch)
    assert inspect.iscoroutinefunction(SettingsRepository.get_for_update)
    assert inspect.iscoroutinefunction(SettingsRepository.replace_all)
    # ``save`` is gone: a whole-blob write must be an explicit import/reset.
    assert not hasattr(SettingsRepository, "save")


class _DoubleRepo:
    """Test double that models the older repository API (``get``/``save``)."""

    def __init__(self, stored: dict | None = None) -> None:
        self.stored = dict(stored or {})
        self.saved: dict | None = None

    async def get(self) -> dict:
        return dict(self.stored)

    async def save(self, values: dict) -> None:
        self.saved = dict(values)
        self.stored = dict(values)


@pytest.mark.asyncio
async def test_patch_helper_merges_for_repository_doubles() -> None:
    repo = _DoubleRepo({"keep": 1, "drop": 2})
    await patch_settings(repo, {"new": 3}, remove=("drop",))
    assert repo.saved == {"keep": 1, "new": 3}


class _RecordingSession:
    def __init__(self) -> None:
        self.executed: list[object] = []

    async def execute(self, statement: object) -> None:
        self.executed.append(statement)


@pytest.mark.asyncio
async def test_patch_skips_the_database_when_nothing_changes() -> None:
    session = _RecordingSession()
    repo = SettingsRepository(session)  # type: ignore[arg-type]
    await repo.patch({})
    assert session.executed == []
