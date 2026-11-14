"""Dead HTTP routes removed in Batch 2 must stay gone.

T2.5 drops four gallery routes that had no callers. The route table is the
contract: checking ``app.routes`` catches both a missing decorator and an
accidental re-registration. The GET favourite-status route and the PUT
progress route stay because the frontend still uses them.
"""

from __future__ import annotations

from galleryvault.app.main import app


def _iter_routes(routes):
    for route in routes:
        # FastAPI keeps included routers lazy: newer versions expose them as
        # ``_IncludedRouter`` wrappers instead of copying the child routes.
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_routes(original.routes)
            continue
        nested = getattr(route, "routes", None)
        if nested:
            yield from _iter_routes(nested)
            continue
        yield route


def _registered(method: str, path: str) -> bool:
    for route in _iter_routes(app.routes):
        methods = getattr(route, "methods", None) or set()
        if getattr(route, "path", None) == path and method in methods:
            return True
    return False


def test_removed_gallery_routes() -> None:
    removed = [
        ("GET", "/api/galleries/categories"),
        ("POST", "/api/galleries/{identifier}/favorite"),
        ("POST", "/api/galleries/{identifier}/read"),
        ("POST", "/api/galleries/{identifier}/progress"),
    ]
    for method, path in removed:
        assert not _registered(method, path), f"{method} {path} should be removed"


def test_preserved_gallery_routes() -> None:
    preserved = [
        ("GET", "/api/galleries/{identifier}/favorite"),
        ("PUT", "/api/galleries/{identifier}/progress"),
    ]
    for method, path in preserved:
        assert _registered(method, path), f"{method} {path} should stay registered"
