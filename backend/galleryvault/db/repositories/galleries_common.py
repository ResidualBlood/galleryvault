"""Module-level helpers extracted from ``galleries.py`` (behaviour-preserving move).

``db.repositories.galleries`` re-exports every name defined here, so existing
import sites (``services.integrity_worker``, ``services.tag_sync``) and the
module-attribute monkeypatches in the test suite keep working unchanged.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Gallery, GalleryTag, Tag

# Cache title sort column per display mode (japanese/english/directory).
# Lazily computed to avoid per-call recomputation when title_display hasn't changed.
_TITLE_SORT_COL_CACHE: dict[str, object] = {}


def _title_sort_column(title_display: str | None = None) -> object:
    """Return column/expression for title sorting per title_display setting."""
    try:
        if title_display:
            mode = title_display.lower()
        else:
            from ...config import get_settings

            settings = get_settings()
            mode = (getattr(settings, "title_display", "japanese") or "japanese").lower()
        if mode not in _TITLE_SORT_COL_CACHE:
            if mode in {"japanese", "directory"}:
                _TITLE_SORT_COL_CACHE[mode] = func.coalesce(Gallery.title_jpn, Gallery.title)
            else:
                _TITLE_SORT_COL_CACHE[mode] = Gallery.title
        return _TITLE_SORT_COL_CACHE[mode]
    except Exception:  # noqa: BLE001
        return Gallery.title


_IMAGE_MAGIC_PREFIXES = (b"RIFF", b"\xff\xd8\xff", b"\x89PNG", b"GIF8")


def _is_valid_page_header(header: bytes) -> bool:
    if not header or len(header) < 20:
        return False
    window = header[:20]
    if window == b"\x00" * 20:
        return False
    return window.startswith(_IMAGE_MAGIC_PREFIXES)


def _session_dialect(session: AsyncSession) -> str:
    """Best-effort bind dialect name (PostgreSQL in prod, SQLite in tests)."""
    try:
        bind = session.get_bind()
    except Exception:  # noqa: BLE001
        return ""
    return getattr(getattr(bind, "dialect", None), "name", "") or ""


def _dialect_insert(session: AsyncSession, model: Any) -> tuple[Any, Any]:
    """Return ``(insert_ctor, greatest)`` for the session's dialect.

    The upserts below rely on ``INSERT .. ON CONFLICT DO UPDATE``.  PostgreSQL
    exposes ``GREATEST``; SQLite (used by the unit-test suite) only has the
    two-argument scalar ``max`` and needs its own insert flavour.
    """
    if _session_dialect(session) == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        return sqlite_insert(model), func.max
    return pg_insert(model), func.greatest


async def _upsert_uploader_tag(
    session: AsyncSession, pairs: Sequence[tuple[int, str | None]]
) -> None:
    """Ensure galleries have tags(namespace='uploader') and matching gallery_tags."""
    valid_pairs = [
        (gid, str(uploader).strip())
        for gid, uploader in pairs
        if gid is not None and uploader is not None and str(uploader).strip()
    ]
    if not valid_pairs:
        return

    unique_uploaders = {u for _, u in valid_pairs}
    await session.execute(
        pg_insert(Tag)
        .values([{"namespace": "uploader", "name": name} for name in unique_uploaders])
        .on_conflict_do_nothing(index_elements=["namespace", "name"])
    )
    await session.flush()

    tag_rows = (
        await session.scalars(
            select(Tag).where(
                Tag.namespace == "uploader", Tag.name.in_(unique_uploaders)
            )
        )
    ).all()
    tag_by_name = {tag.name: tag.id for tag in tag_rows}

    gallery_ids = list({gid for gid, _ in valid_pairs})
    old_uploader_tag_ids = select(Tag.id).where(Tag.namespace == "uploader")
    await session.execute(
        delete(GalleryTag).where(
            GalleryTag.gallery_id.in_(gallery_ids),
            GalleryTag.tag_id.in_(old_uploader_tag_ids),
        )
    )

    gallery_tag_values = [
        {"gallery_id": gid, "tag_id": tag_by_name[u]}
        for gid, u in valid_pairs
        if u in tag_by_name
    ]
    if gallery_tag_values:
        await session.execute(
            pg_insert(GalleryTag)
            .values(gallery_tag_values)
            .on_conflict_do_nothing(index_elements=["gallery_id", "tag_id"])
        )
    await session.flush()
