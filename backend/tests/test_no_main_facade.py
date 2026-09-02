"""Guard test: Ensure production code and tests do not depend on app.main facade."""

from __future__ import annotations

import ast
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = BACKEND_ROOT / "galleryvault"
TESTS_ROOT = BACKEND_ROOT / "tests"


def _check_ast_for_main_import(file_path: Path) -> list[str]:
    violations: list[str] = []
    source = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            is_main_module = module == "main" or module.endswith(".main")
            is_main_symbol = (node.level > 0 and module in ("", "app") and any(a.name == "main" for a in node.names)) or \
                (module in ("galleryvault.app",) and any(a.name == "main" for a in node.names))
            if is_main_module or is_main_symbol:
                violations.append(f"{file_path}:{node.lineno}: import from main ({ast.unparse(node)})")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith(".main") or alias.name == "main":
                    violations.append(f"{file_path}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "setattr"):
            if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "main":
                violations.append(f"{file_path}:{node.lineno}: {node.func.id}(main, ...)")
    return violations


def _check_tests_for_main_monkeypatch(file_path: Path) -> list[str]:
    violations: list[str] = []
    source = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        # Check monkeypatch.setattr(main, ...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setattr":
            if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "main":
                violations.append(f"{file_path}:{node.lineno}: monkeypatch.setattr(main, ...)")
            elif node.args and isinstance(node.args[0], ast.Attribute) and isinstance(node.args[0].value, ast.Name) and node.args[0].value.id == "main":
                violations.append(f"{file_path}:{node.lineno}: monkeypatch.setattr(main.X, ...)")
        # Check from galleryvault.app import main
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in ("galleryvault.app",) and any(a.name == "main" for a in node.names):
                violations.append(f"{file_path}:{node.lineno}: from galleryvault.app import main")
    return violations


def test_production_code_has_no_main_facade_references():
    """Verify that galleryvault/ codebase (excluding app/main.py) does not import or inspect main."""
    all_violations: list[str] = []
    for root, _, files in os.walk(PACKAGE_ROOT):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = Path(root) / f
            if path.resolve() == (PACKAGE_ROOT / "app" / "main.py").resolve():
                continue
            violations = _check_ast_for_main_import(path)
            all_violations.extend(violations)

    assert not all_violations, "Found forbidden main references in production code:\n" + "\n".join(all_violations)


def test_tests_have_no_main_monkeypatch_or_facade_imports():
    """Verify that tests/ codebase does not monkeypatch main or import main facade."""
    all_violations: list[str] = []
    for root, _, files in os.walk(TESTS_ROOT):
        for f in files:
            if not f.endswith(".py") or f == "test_no_main_facade.py":
                continue
            path = Path(root) / f
            violations = _check_tests_for_main_monkeypatch(path)
            all_violations.extend(violations)

    assert not all_violations, "Found forbidden main monkeypatches in tests:\n" + "\n".join(all_violations)
