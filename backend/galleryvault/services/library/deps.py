"""Collaborators injected into the library use-cases by the router layer.

The router resolves its monkeypatchable module globals (``GalleryRepository``,
``delete_galleries_local``, ``_record_gallery_delete_log``, serialisers) at
call time and passes them here.  This keeps
``monkeypatch.setattr(galleries, ...)`` effective without importing
``galleryvault.app`` from the use-case modules.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

__all__ = ["LibraryDeps"]


@dataclass(frozen=True)
class LibraryDeps:
    """Request-scoped collaborators for listing and filtered deletion."""

    repo_factory: Callable[[Any], Any]
    # Listing: row -> response payload and tolerant attribute access.
    serialize_summary: Callable[..., dict[str, Any]] | None = None
    attr: Callable[[Any, str, Any], Any] | None = None
    # Filtered deletion.
    delete_local: Callable[..., Awaitable[list[dict[str, Any]]]] | None = None
    record_delete_log: Callable[[list[dict[str, Any]], bool], None] | None = None
