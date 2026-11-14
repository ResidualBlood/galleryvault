"""The frontend may only call endpoints the backend actually serves.

Every endpoint is declared once with ``ep("METHOD", "/api/...")`` in
``frontend/src/api/*.ts`` (see ``client.ts``).  This test compares those
declarations against the route table FastAPI registered, so a rename or a
removed handler fails at test time instead of as a 404 in the browser.

Path parameter *names* are irrelevant to routing (``{gid}`` and
``{identifier}`` describe the same shape), and a literal segment may legitimately
fill a path parameter (``/api/logs/archive/cancel`` targets
``/api/logs/{task}/cancel``).  Both are accepted; a path that no route template
can match is not.

The container image has no ``frontend/`` checkout, so this module skips there.
CI runs it from the repository root (T7.3), where the frontend sources exist.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pytest

from galleryvault.app.main import app

_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_API_DIR = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api"
_EP_PATTERN = re.compile(
    r"""\bep\(\s*["'](GET|POST|PUT|PATCH|DELETE)["']\s*,\s*["']([^"']+)["']"""
)

# Deliberate exceptions, keyed by (METHOD, declared path).  Empty on purpose:
# the contract is that the frontend never calls a route the backend lacks.
ENDPOINT_EXEMPTIONS: dict[tuple[str, str], str] = {}


def _iter_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Flatten FastAPI's lazily included routers into leaf routes."""
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_routes(original.routes)
            continue
        nested = getattr(route, "routes", None)
        if nested:
            yield from _iter_routes(nested)
            continue
        yield route


def _registered_operations() -> set[tuple[str, str]]:
    operations: set[tuple[str, str]] = set()
    for route in _iter_routes(app.routes):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if not path:
            continue
        for method in methods & _HTTP_METHODS:
            operations.add((method, path))
    return operations


def _route_matcher(route_path: str) -> re.Pattern[str]:
    """Compile a route template so any one path segment can fill a parameter."""
    parts: list[str] = []
    for segment in route_path.split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            parts.append("[^/]+")
        else:
            parts.append(re.escape(segment))
    return re.compile("^" + "/".join(parts) + "$")


def _matches(method: str, declared: str, operations: set[tuple[str, str]]) -> bool:
    if (method, declared) in operations:
        return True
    # A literal segment is a valid value for a path parameter.  Normalising the
    # parameter name alone would reject e.g. /api/logs/archive/cancel, which the
    # server routes to /api/logs/{task}/cancel.
    return any(
        op_method == method and _route_matcher(op_path).fullmatch(declared)
        for op_method, op_path in operations
    )


def _declarations() -> list[tuple[str, str, str, int]]:
    declarations: list[tuple[str, str, str, int]] = []
    for path in sorted(_API_DIR.glob("*.ts")):
        if path.name.endswith(".test.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        for match in _EP_PATTERN.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            declarations.append(
                (match.group(1), match.group(2), path.name, line)
            )
    return declarations


def test_frontend_endpoints_exist() -> None:
    if not _API_DIR.is_dir():
        pytest.skip(f"frontend api directory not available: {_API_DIR}")

    declarations = _declarations()
    assert declarations, f"no ep() declarations found in {_API_DIR}"

    operations = _registered_operations()
    missing: list[str] = []
    for method, declared, filename, line in declarations:
        if (method, declared) in ENDPOINT_EXEMPTIONS:
            continue
        if _matches(method, declared, operations):
            continue
        missing.append(f"{method} {declared} ({filename}:{line})")

    assert not missing, (
        "frontend declares endpoints the backend does not serve:\n  "
        + "\n  ".join(missing)
    )
