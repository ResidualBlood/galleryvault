"""T2.6: dead favorites routes are gone; live entrypoints stay reachable.

Removed in this task (INV-API-1, no caller):
  POST /api/favorites/sync                (no-op alias)
  POST /api/favorites/check               (alias, ``{favcat}/check`` kept)
  POST /api/favorites/compute-sizes       (size sync still runs via download-missing)
  GET  /api/favorites/metadata-status     (internal task state)
  POST /api/favorites/fetch-categories    (alias, /sync-categories kept)
  POST /api/favorites/categories          (GET kept: userscript + frontend)

Kept: GET /api/favorites/categories, POST /api/favorites/{favcat}/check,
POST /api/favorites/sync-categories, POST /api/favorites/check-all,
GET /api/favorites/check-status, POST /api/favorites/download-missing.
"""

from __future__ import annotations

from galleryvault.app.routers import favorites

REMOVED_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/favorites/sync"),
    ("POST", "/api/favorites/check"),
    ("POST", "/api/favorites/compute-sizes"),
    ("GET", "/api/favorites/metadata-status"),
    ("POST", "/api/favorites/fetch-categories"),
    ("POST", "/api/favorites/categories"),
)

KEPT_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/api/favorites/categories"),
    ("POST", "/api/favorites/{favcat}/check"),
    ("POST", "/api/favorites/sync-categories"),
    ("POST", "/api/favorites/check-all"),
    ("GET", "/api/favorites/check-status"),
    ("POST", "/api/favorites/download-missing"),
)


def _route_table() -> set[tuple[str, str]]:
    table: set[tuple[str, str]] = set()
    for route in favorites.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if not path:
            continue
        for method in methods:
            table.add((method.upper(), str(path)))
    return table


def test_removed_favorites_routes_are_gone() -> None:
    table = _route_table()
    still_present = [(m, p) for m, p in REMOVED_ROUTES if (m, p) in table]
    assert still_present == []


def test_live_favorites_routes_are_kept() -> None:
    table = _route_table()
    missing = [(m, p) for m, p in KEPT_ROUTES if (m, p) not in table]
    assert missing == []


def test_sync_favorite_categories_still_importable_for_tgbot() -> None:
    from galleryvault.app.routers.favorites import sync_favorite_categories

    assert callable(sync_favorite_categories)
