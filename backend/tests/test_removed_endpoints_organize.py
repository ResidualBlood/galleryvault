"""T2.7: dead organize GET routes are gone, write routes stay reachable.

Q4 keeps list rename/delete, manual series items, and tag-sync status/refresh
(their front-end entries land in T2.9). Only the two unused detail GET routes
are removed, so the retained handlers must still be registered.
"""

from __future__ import annotations

from galleryvault.app.main import app

REMOVED: tuple[tuple[str, str], ...] = (
    ("GET", "/api/lists/{list_id}"),
    ("GET", "/api/series/{series_id}"),
)

KEPT: tuple[tuple[str, str], ...] = (
    ("GET", "/api/lists"),
    ("POST", "/api/lists"),
    ("PATCH", "/api/lists/{list_id}"),
    ("DELETE", "/api/lists/{list_id}"),
    ("POST", "/api/lists/{list_id}/items"),
    ("POST", "/api/lists/{list_id}/items/remove"),
    ("GET", "/api/series"),
    ("POST", "/api/series"),
    ("PATCH", "/api/series/{series_id}"),
    ("DELETE", "/api/series/{series_id}"),
    ("POST", "/api/series/{series_id}/items"),
    ("POST", "/api/series/{series_id}/items/remove"),
    ("GET", "/api/tag-sync/status"),
    ("POST", "/api/tag-sync/refresh-categories"),
)


def _registered_routes() -> set[tuple[str, str]]:
    # FastAPI lazily mounts included routers, so the OpenAPI schema is the
    # authoritative view of what the running API actually exposes.
    registered: set[tuple[str, str]] = set()
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            registered.add((method.upper(), path))
    return registered


def test_removed_organize_routes_are_gone() -> None:
    registered = _registered_routes()
    still_present = [sig for sig in REMOVED if sig in registered]
    assert not still_present, f"dead routes still registered: {still_present}"


def test_retained_organize_routes_remain() -> None:
    registered = _registered_routes()
    missing = [sig for sig in KEPT if sig not in registered]
    assert not missing, f"retained routes disappeared: {missing}"
