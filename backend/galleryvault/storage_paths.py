"""Filesystem helpers shared by the db layer and cold-storage services.

Kept free of service imports so ``db.repositories.galleries_ingest`` can decide
a storage tier without importing ``services.cold_archive``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def resolve_archive_roots(
    archive_roots: Sequence[Path | str] | None = None,
    cold_root: Path | str | None = None,
) -> list[Path]:
    """Resolve archive roots from parameters or settings with backwards compatibility.

    - If explicit archive_roots are provided, use them.
    - Else if explicit cold_root is provided, wrap in a single-item list.
    - Otherwise, read settings.archive_roots; if empty, read settings.cold_storage_root.
    - Returns resolved, non-empty, deduplicated Path objects.
    """
    candidates: list[str | Path] = []
    if archive_roots is not None:
        candidates = list(archive_roots)
    elif cold_root is not None:
        cr_str = str(cold_root).strip()
        if cr_str:
            candidates = [cr_str]
    else:
        from .app.state import app_state
        from .config import get_settings

        settings = app_state.settings or get_settings()
        roots = getattr(settings, "archive_roots", []) or []
        if not roots:
            cr = (getattr(settings, "cold_storage_root", None) or "").strip()
            if cr:
                roots = [cr]
        candidates = list(roots)

    result: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        s = str(item).strip()
        if not s:
            continue
        p = Path(s).resolve()
        key = str(p)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def is_under_cold(
    path: Path | str,
    cold_roots: Path | str | Sequence[Path | str] | None = None,
) -> bool:
    """Check whether a path is already located under any cold storage root."""
    try:
        resolved = Path(path).resolve()
        if cold_roots is None:
            roots = resolve_archive_roots()
        elif isinstance(cold_roots, (Path, str)):
            roots = [Path(cold_roots).resolve()]
        else:
            roots = [Path(r).resolve() for r in cold_roots]
        for c in roots:
            if resolved == c or resolved.is_relative_to(c):
                return True
        return False
    except (ValueError, OSError):
        return False
