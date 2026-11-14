"""Maintenance endpoints: favourites duplicate review and gallery integrity.

The handlers live in :mod:`favorite_duplicates` and :mod:`integrity`; the
owning routers include them at the exact registration positions the handlers
occupied before the split, so URL paths, route resolution order, the OpenAPI
snapshot and ``monkeypatch.setattr`` on the original router modules keep
working.
"""

from __future__ import annotations

from . import favorite_duplicates, integrity

__all__ = ["favorite_duplicates", "integrity"]
