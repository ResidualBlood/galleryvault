"""Route resolution order is part of the API contract.

Endpoint functions may move between modules during the service splits, but the
``(method, path template) -> first matching endpoint`` mapping must not change.
A newly included router that shadows an older route (for example
``DELETE /api/galleries/{identifier}`` registered before
``DELETE /api/galleries/progress``) would silently route a request to the wrong
handler while every endpoint still exists.

The golden file records, for every route in ``app.routes``, the ``__name__`` of
the endpoint that Starlette selects first.  It is intentionally keyed by
template + method only, so pure file/module moves do not require regeneration.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from starlette.routing import Match

from galleryvault.app.main import app

GOLDEN = Path(__file__).resolve().parent / "golden" / "route_resolution.json"


def _iter_effective_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Flatten lazily included routers in registration order."""
    for route in routes:
        effective = getattr(route, "effective_route_contexts", None)
        if effective is not None:
            yield from effective()
            continue
        nested = getattr(route, "original_router", None)
        if nested is not None:
            yield from _iter_effective_routes(nested.routes)
            continue
        yield route


def _concrete_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def _first_matching_endpoint(route: Any, method: str, path: str) -> str | None:
    scope = {
        "type": "http",
        "method": method,
        "path": _concrete_path(path),
        "root_path": "",
        "headers": [],
        "query_string": b"",
        "app": app,
    }
    match, _ = route.matches(scope)
    if match is not Match.FULL:
        return None
    endpoint = getattr(route, "endpoint", None)
    return getattr(endpoint, "__name__", type(route).__name__)


def collect_route_resolution() -> dict[str, str]:
    """Return ``"METHOD /path/template" -> first endpoint name`` in match order."""
    routes = list(_iter_effective_routes(app.routes))
    resolution: dict[str, str] = {}
    for candidate in routes:
        path = getattr(candidate, "path", None)
        methods = getattr(candidate, "methods", None) or set()
        if not path:
            continue
        for method in methods:
            first = None
            for route in routes:
                if method not in (getattr(route, "methods", None) or set()):
                    continue
                first = _first_matching_endpoint(route, method, path)
                if first is not None:
                    break
            assert first is not None, f"{method} {path} did not match any route"
            resolution[f"{method} {path}"] = first
    return dict(sorted(resolution.items()))


def test_route_resolution_matches_golden() -> None:
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = collect_route_resolution()

    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    shadowed = sorted(
        (key, expected[key], actual[key])
        for key in set(expected) & set(actual)
        if expected[key] != actual[key]
    )
    assert not missing and not unexpected and not shadowed, (
        "route resolution changed; regenerate "
        "backend/tests/contract/golden/route_resolution.json only if the route "
        "table intentionally changed.\n"
        f"missing: {missing}\n"
        f"unexpected: {unexpected}\n"
        f"shadowed (key, expected, actual): {shadowed}"
    )
