from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, case, delete, false, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...scanners.base import ExistingGallery, GalleryMeta, normalize_category
from ..models import (
    DuplicateRecord,
    FavoriteItem,
    Gallery,
    GalleryMetadata,
    GalleryPage,
    GalleryTag,
    GalleryUpdate,
    ReadingHistory,
    ReadingProgress,
    Tag,
)
from .base import _chunked, escape_like_wildcards, path_hash

# Cache title sort column per display mode (japanese/english/directory).
# Lazily computed to avoid importing app_state at module load and to avoid
# per-call recomputation when title_display hasn't changed.
_TITLE_SORT_COL_CACHE: dict[str, object] = {}


def _title_sort_column() -> object:
    """Return column/expression for title sorting per title_display setting."""
    try:
        from ...app.state import app_state
        from ...config import get_settings

        settings = app_state.settings or get_settings()
        mode = (getattr(settings, "title_display", "japanese") or "japanese").lower()
        if mode not in _TITLE_SORT_COL_CACHE:
            if mode in {"japanese", "directory"}:
                _TITLE_SORT_COL_CACHE[mode] = func.coalesce(Gallery.title_jpn, Gallery.title)
            else:
                _TITLE_SORT_COL_CACHE[mode] = Gallery.title
        return _TITLE_SORT_COL_CACHE[mode]
    except Exception:  # noqa: BLE001
        return Gallery.title


class GalleryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_many(self, galleries: Sequence[GalleryMeta]) -> None:
        """Ingest one scanner batch with one flush and set-based relation writes."""
        if not galleries:
            return
        unique: dict[tuple[str, object], GalleryMeta] = {}
        for gallery in galleries:
            key = (
                ("gid", gallery.gid)
                if gallery.gid is not None
                else ("path", path_hash(gallery.path))
            )
            unique[key] = gallery
        values_by_key = {
            key: {
                "gid": gallery.gid,
                "token": gallery.token,
                "title": gallery.title,
                "title_jpn": gallery.title_jpn,
                "category": gallery.category,
                "uploader": gallery.uploader,
                "file_count": gallery.file_count,
                "file_size": gallery.file_size,
                "rating": gallery.rating,
                "posted_at": gallery.posted_at,
                "storage_type": gallery.storage_type,
                "storage_path": str(gallery.path),
                "path_hash": path_hash(gallery.path),
                "storage_mtime_ns": gallery.storage_mtime_ns,
                "storage_size": gallery.storage_size,
                "storage_signature": gallery.storage_signature,
                "image_quality": gallery.image_quality,
                "expunged": False,
                "cover_path": gallery.pages[0].name if gallery.pages else None,
                "page_count": len(gallery.pages),
                "source_meta": {**gallery.source_meta, "warnings": gallery.warnings},
                "updated_at": datetime.now(UTC),
            }
            for key, gallery in unique.items()
        }
        gids = [gallery.gid for gallery in unique.values() if gallery.gid is not None]
        hashes = [path_hash(gallery.path) for gallery in unique.values()]
        # Build the lookup conditionally: ``False | column.in_(...)`` raises
        # ``TypeError`` (a Python bool has no ``__ror__``), so a batch of only
        # gid-less galleries (e.g. calibre CBZ exports) must not produce one.
        where: list[object] = []
        if gids:
            where.append(Gallery.gid.in_(gids))
        if hashes:
            where.append(Gallery.path_hash.in_(hashes))
        stmt = (
            select(Gallery).where(or_(*where))
            if where
            else select(Gallery).where(false())
        )
        existing = list((await self.session.scalars(stmt)).all())
        by_key = {
            ("gid", row.gid) if row.gid is not None else ("path", row.path_hash): row
            for row in existing
        }
        changed: list[tuple[Gallery, GalleryMeta]] = []
        for key, gallery in unique.items():
            row = by_key.get(key)
            if row is None:
                row = Gallery(**values_by_key[key])
                self.session.add(row)
                changed.append((row, gallery))
            elif row.storage_signature != gallery.storage_signature or row.expunged:
                for name, value in values_by_key[key].items():
                    if name == "image_quality" and value is None:
                        # Keep an already-known quality: a re-scan of a download
                        # without a fresh quality marker must not erase it.
                        continue
                    setattr(row, name, value)
                changed.append((row, gallery))
        if changed:
            await self.session.flush()
        if not changed:
            return
        changed_ids = [row.id for row, _ in changed]
        await self.session.execute(
            delete(GalleryPage).where(GalleryPage.gallery_id.in_(changed_ids))
        )
        await self.session.execute(delete(GalleryTag).where(GalleryTag.gallery_id.in_(changed_ids)))
        page_rows = []
        tag_keys: set[tuple[str, str]] = set()
        for row, gallery in changed:
            page_rows.extend(
                GalleryPage(
                    gallery_id=row.id,
                    page_index=page.index,
                    member_name=page.name,
                    media_type=page.media_type,
                    manifest={"size": page.size, "mtime_ns": page.mtime_ns},
                )
                for page in gallery.pages
            )
            tag_keys.update(
                (
                    str(item.get("namespace", "misc")).strip() or "misc",
                    str(item.get("name", "")).strip(),
                )
                for item in gallery.tags
                if str(item.get("name", "")).strip()
            )
        if page_rows:
            self.session.add_all(page_rows)
        if tag_keys:
            tag_rows = list(
                (
                    await self.session.scalars(
                        select(Tag).where(tuple_(Tag.namespace, Tag.name).in_(tag_keys))
                    )
                ).all()
            )
            tag_map = {(tag.namespace, tag.name): tag for tag in tag_rows}
            missing = [
                Tag(namespace=ns, name=name) for ns, name in tag_keys if (ns, name) not in tag_map
            ]
            if missing:
                await self.session.execute(
                    pg_insert(Tag)
                    .values([{"namespace": tag.namespace, "name": tag.name} for tag in missing])
                    .on_conflict_do_nothing(index_elements=["namespace", "name"])
                )
                tag_rows = list(
                    (
                        await self.session.scalars(
                            select(Tag).where(tuple_(Tag.namespace, Tag.name).in_(tag_keys))
                        )
                    ).all()
                )
                tag_map = {(tag.namespace, tag.name): tag for tag in tag_rows}
            self.session.add_all(
                GalleryTag(gallery_id=row.id, tag_id=tag_map[key].id)
                for row, gallery in changed
                for key in {
                    (
                        str(item.get("namespace", "misc")).strip() or "misc",
                        str(item.get("name", "")).strip(),
                    )
                    for item in gallery.tags
                    if str(item.get("name", "")).strip()
                }
            )
        await self.session.flush()

    async def existing_rows(self, roots: Sequence[str | Path]) -> dict[str, ExistingGallery]:
        """Return path hash -> gallery row for non-expunged rows under ``roots``.

        The richer payload (gid, title, size, posted date...) lets the library
        scanner both skip unchanged copies by signature and fold already-ingested
        copies into duplicate-copy resolution.  Streams with ``yield_per`` so a
        library of hundreds of thousands of galleries never materialises every
        ``Gallery`` ORM object at once.
        """
        if not roots:
            return {}
        normalized = [str(Path(root).resolve()) for root in roots]
        # Coarse SQL prefilter: only stream rows whose stored path could live
        # under one of the roots, instead of pulling the whole non-expunged
        # table.  The resolved ``is_relative_to`` check below stays authoritative.
        result = await self.session.stream(
            select(
                Gallery.path_hash,
                Gallery.storage_signature,
                Gallery.storage_path,
                Gallery.gid,
                Gallery.id,
                Gallery.storage_type,
                Gallery.title,
                Gallery.title_jpn,
                Gallery.file_count,
                Gallery.file_size,
                Gallery.posted_at,
            ).where(
                and_(
                    Gallery.expunged.is_(False),
                    or_(*(Gallery.storage_path.startswith(root) for root in normalized)),
                )
            )
        )
        out: dict[str, ExistingGallery] = {}
        async for row in result:
            m = row._mapping
            path = m["storage_path"]
            if any(Path(path).resolve().is_relative_to(root) for root in normalized):
                out[m["path_hash"]] = ExistingGallery(
                    path=path,
                    signature=m["storage_signature"],
                    gid=m["gid"],
                    gallery_id=m["id"],
                    storage_type=m["storage_type"],
                    title=m["title"],
                    title_jpn=m["title_jpn"],
                    file_count=m["file_count"],
                    file_size=m["file_size"],
                    posted_at=m["posted_at"],
                )
        return out

    async def sync_duplicates(self, groups) -> int:
        """Persist the duplicate groups a scan just produced.

        Open records are refreshed with the current copies; records the user
        dismissed or resolved are left alone (their decision wins).  Records
        whose gid is no longer duplicated (copy removed on disk, or resolved
        for real) are deleted.
        """
        from ..services.duplicate_resolver import ResolvedGroup

        groups = [group for group in groups if isinstance(group, ResolvedGroup)]
        current = {group.gid for group in groups}
        rows = list((await self.session.scalars(select(DuplicateRecord))).all())
        by_gid = {row.gid: row for row in rows}
        # Reconcile each copy against the row the gallery currently points at, so
        # the cleanup page can show which copy is the ingested one (thumbnail /
        # "current" badge) even when the winner was ingested mid-scan.
        live_rows = list(
            (
                await self.session.scalars(
                    select(Gallery).where(Gallery.gid.in_(list(current)))
                )
            ).all()
        )
        live_by_gid = {row.gid: row for row in live_rows}
        changed = 0
        for group in groups:
            payload = group.record()
            live = live_by_gid.get(group.gid)
            for copy in payload["copies"]:
                copy["is_current"] = live is not None and copy["path"] == live.storage_path
                copy["gallery_id"] = live.id if live is not None and copy["path"] == live.storage_path else copy.get("gallery_id")
            record = by_gid.get(group.gid)
            if record is None:
                self.session.add(
                    DuplicateRecord(
                        gid=group.gid,
                        status="open",
                        policy=payload["policy"],
                        winner_path=payload["winner_path"],
                        copies=payload["copies"],
                    )
                )
                changed += 1
            elif record.status == "open":
                record.policy = payload["policy"]
                record.winner_path = payload["winner_path"]
                record.copies = payload["copies"]
                record.updated_at = datetime.now(UTC)
                changed += 1
        for gid, record in by_gid.items():
            if gid not in current:
                await self.session.delete(record)
                changed += 1
        await self.session.flush()
        return changed

    async def list_duplicates(self) -> list[dict[str, object]]:
        rows = list(
            (
                await self.session.scalars(
                    select(DuplicateRecord).order_by(DuplicateRecord.updated_at.desc())
                )
            ).all()
        )
        return [
            {
                "gid": row.gid,
                "status": row.status,
                "policy": row.policy,
                "winner_path": row.winner_path,
                "copies": row.copies or [],
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]

    async def set_duplicate_status(self, gid: int, status: str) -> bool:
        row = await self.session.get(DuplicateRecord, gid)
        if row is None:
            return False
        row.status = status
        row.updated_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def delete_duplicate(self, gid: int) -> bool:
        row = await self.session.get(DuplicateRecord, gid)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def duplicate_copies_for_gid(self, gid: int) -> list[dict[str, object]]:
        """Return the on-disk copy paths recorded for a duplicate group."""
        row = await self.session.get(DuplicateRecord, gid)
        return row.copies or [] if row is not None else []

    async def expunge_missing(self, roots: Sequence[str | Path], seen: set[str]) -> int:
        normalized = [str(Path(root).resolve()) for root in roots]
        result = await self.session.stream(
            select(Gallery.id, Gallery.path_hash, Gallery.storage_path).where(
                Gallery.expunged.is_(False), Gallery.trashed.is_(False)
            )
        )
        missing_ids: list[int] = []
        async for row in result:
            m = row._mapping
            path = Path(m["storage_path"]).resolve()
            if any(path.is_relative_to(root) for root in normalized) and m["path_hash"] not in seen:
                missing_ids.append(m["id"])
        for start in range(0, len(missing_ids), 5000):
            await self._mark_expunged(missing_ids[start : start + 5000])
        await self.session.flush()
        return len(missing_ids)

    async def _mark_expunged(self, ids: list[int]) -> None:
        await self.session.execute(
            update(Gallery)
            .where(Gallery.id.in_(ids))
            .values(expunged=True, updated_at=datetime.now(UTC))
        )

    async def list_page(
        self,
        page: int,
        page_size: int,
        q: str | None = None,
        tags: Sequence[tuple[str | None, str]] = (),
        exclude_tags: Sequence[tuple[str | None, str]] = (),
        tag_mode: str = "or",
        tag_match: str = "exact",
        category: str | None = None,
        exclude_favorited: bool = False,
        order_by: str = "id_desc",
        read_status: str | None = None,
        min_rating: float | None = None,
        page_min: int | None = None,
        page_max: int | None = None,
    ) -> tuple[int, list[Gallery]]:
        query = select(Gallery)
        if q and q.strip():
            # Multiple free-form tokens are ANDed as separate substrings rather
            # than one contiguous pattern, so "mimu gif" matches any title that
            # contains both words anywhere (order- and position-independent).
            for token in q.split():
                pattern = f"%{escape_like_wildcards(token)}%"
                query = query.where(Gallery.title.ilike(pattern) | Gallery.title_jpn.ilike(pattern))
        if category:
            query = query.where(Gallery.category == category)
        if min_rating is not None:
            query = query.where(Gallery.rating >= min_rating)
        if page_min is not None:
            query = query.where(Gallery.page_count >= page_min)
        if page_max is not None:
            query = query.where(Gallery.page_count <= page_max)
        if exclude_favorited:
            # Local galleries whose gid is not in any favorite folder and
            # not superseded by a tracked update whose new_gid is in favorites.
            fav_exists = select(1).select_from(FavoriteItem).where(FavoriteItem.gid == Gallery.gid)
            updated_fav_exists = (
                select(1)
                .select_from(GalleryUpdate)
                .join(FavoriteItem, FavoriteItem.gid == GalleryUpdate.new_gid)
                .where(
                    GalleryUpdate.gallery_id == Gallery.id,
                    GalleryUpdate.status != "ignored",
                )
            )
            query = query.where(
                Gallery.gid.is_(None)
                | (
                    ~fav_exists.exists()
                    & ~updated_fav_exists.exists()
                )
            )
        if read_status == "unread":
            prog_exists = select(1).select_from(ReadingProgress).where(
                ReadingProgress.gallery_id == Gallery.id,
                ReadingProgress.current_page > 0,
            )
            query = query.where(~prog_exists.exists())
        elif read_status == "reading":
            prog_exists = select(1).select_from(ReadingProgress).where(
                ReadingProgress.gallery_id == Gallery.id,
                ReadingProgress.current_page > 0,
                (
                    ReadingProgress.total_pages.is_(None)
                    | (ReadingProgress.current_page < ReadingProgress.total_pages - 1)
                ),
            )
            query = query.where(prog_exists.exists())
        elif read_status in {"completed", "read"}:
            prog_exists = select(1).select_from(ReadingProgress).where(
                ReadingProgress.gallery_id == Gallery.id,
                ReadingProgress.total_pages.is_not(None),
                ReadingProgress.current_page >= ReadingProgress.total_pages - 1,
            )
            query = query.where(prog_exists.exists())
        if tags:
            tag_conditions = []
            for namespace, name in tags:
                escaped_name = escape_like_wildcards(name)
                pattern = escaped_name if tag_match == "exact" else f"%{escaped_name}%"
                condition = [Tag.name.ilike(pattern)]
                if namespace:
                    condition.append(Tag.namespace == namespace)
                tag_conditions.append(
                    select(GalleryTag.gallery_id)
                    .join(Tag, Tag.id == GalleryTag.tag_id)
                    .where(GalleryTag.gallery_id == Gallery.id, *condition)
                )
            if tag_mode == "and":
                query = query.where(*[subquery.exists() for subquery in tag_conditions])
            else:
                query = query.where(or_(*[subquery.exists() for subquery in tag_conditions]))
        if exclude_tags:
            for namespace, name in exclude_tags:
                escaped_name = escape_like_wildcards(name)
                pattern = escaped_name if tag_match == "exact" else f"%{escaped_name}%"
                condition = [Tag.name.ilike(pattern)]
                if namespace:
                    condition.append(Tag.namespace == namespace)
                subquery = (
                    select(GalleryTag.gallery_id)
                    .join(Tag, Tag.id == GalleryTag.tag_id)
                    .where(GalleryTag.gallery_id == Gallery.id, *condition)
                )
                query = query.where(~subquery.exists())
        query = query.where(Gallery.expunged.is_(False), Gallery.trashed.is_(False))
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        title_col = _title_sort_column()
        order_map = {
            "id_desc": [Gallery.id.desc()],
            "id_asc": [Gallery.id.asc()],
            "posted_at_desc": [Gallery.posted_at.desc().nullslast(), Gallery.id.desc()],
            "posted_at_asc": [Gallery.posted_at.asc().nullslast(), Gallery.id.asc()],
            "title_asc": [title_col.asc(), Gallery.id.asc()],
            "title_desc": [title_col.desc(), Gallery.id.desc()],
            "page_count_desc": [Gallery.page_count.desc().nullslast(), Gallery.id.desc()],
            "page_count_asc": [Gallery.page_count.asc().nullslast(), Gallery.id.asc()],
            "file_size_desc": [Gallery.file_size.desc().nullslast(), Gallery.id.desc()],
            "file_size_asc": [Gallery.file_size.asc().nullslast(), Gallery.id.asc()],
            "rating_desc": [Gallery.rating.desc().nullslast(), Gallery.id.desc()],
            "rating_asc": [Gallery.rating.asc().nullslast(), Gallery.id.asc()],
        }
        order_clauses = order_map.get(order_by, [Gallery.id.desc()])
        rows = (
            await self.session.scalars(
                query.order_by(*order_clauses).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        return total, list(rows)

    async def progress_for_galleries(self, gallery_ids: list[int]) -> dict[int, int]:
        if not gallery_ids:
            return {}
        rows = (
            await self.session.scalars(
                select(ReadingProgress).where(ReadingProgress.gallery_id.in_(gallery_ids))
            )
        ).all()
        return {r.gallery_id: r.current_page for r in rows}

    async def next_gallery_id(self, current_id: int) -> int | None:
        """The next non-expunged gallery id after ``current_id`` (ascending)."""
        return await self.session.scalar(
            select(Gallery.id)
            .where(Gallery.id > current_id, Gallery.expunged.is_(False), Gallery.trashed.is_(False))
            .order_by(Gallery.id)
            .limit(1)
        )

    async def search_tags(
        self, q: str | None, page: int, page_size: int, namespace: str | None = None
    ) -> tuple[int, list[tuple[str, str, int]]]:
        pattern = f"%{escape_like_wildcards(q.strip())}%" if q and q.strip() else None
        match = select(Tag.id).select_from(Tag)
        if namespace:
            match = match.where(Tag.namespace == namespace)
        if pattern:
            match = match.where(Tag.name.ilike(pattern) | Tag.namespace.ilike(pattern))
        total = int(await self.session.scalar(select(func.count()).select_from(match.subquery())) or 0)
        # Limit the tag rows first, then compute usage counts only for the
        # visible page — counting usage for every matching tag then slicing was
        # a full-table aggregation on large libraries.
        page_ids = match.order_by(Tag.namespace, Tag.name).offset((page - 1) * page_size).limit(page_size)
        rows = (
            await self.session.execute(
                select(Tag.namespace, Tag.name, func.count(Gallery.id))
                .select_from(Tag)
                .outerjoin(GalleryTag, GalleryTag.tag_id == Tag.id)
                .outerjoin(
                    Gallery,
                    and_(Gallery.id == GalleryTag.gallery_id, Gallery.expunged.is_(False)),
                )
                .where(Tag.id.in_(page_ids))
                .group_by(Tag.id)
                .order_by(Tag.namespace, Tag.name)
            )
        ).all()
        return total, [(namespace, name, int(count)) for namespace, name, count in rows]

    async def resolve_tag_names(
        self, names: list[str]
    ) -> dict[str, list[tuple[str, str, int]]]:
        """Map exact (case-insensitive) English tag names to their tags.

        Returns ``{name.lower(): [(namespace, name, usage_count), ...]}`` where
        each list is ordered by usage count descending (ties by namespace), so
        callers can pick the most representative tag when a name lives in
        several namespaces.  Used by the smart search-box parsing to promote
        plain English tokens that are real tag names into tag filters.
        """
        if not names:
            return {}
        lowered = [n.lower() for n in names]
        rows = await self.session.execute(
            select(
                Tag.namespace,
                Tag.name,
                func.count(Gallery.id),
            )
            .select_from(Tag)
            .outerjoin(GalleryTag, GalleryTag.tag_id == Tag.id)
            .outerjoin(
                Gallery,
                and_(Gallery.id == GalleryTag.gallery_id, Gallery.expunged.is_(False)),
            )
            .where(func.lower(Tag.name).in_(lowered))
            .group_by(Tag.id)
            .order_by(Tag.namespace, Tag.name)
        )
        result: dict[str, list[tuple[str, str, int]]] = {}
        for namespace, name, count in rows.all():
            result.setdefault(name.lower(), []).append((namespace, name, int(count)))
        for candidates in result.values():
            candidates.sort(key=lambda item: (-item[2], item[0]))
        return result

    async def tag_facets(self) -> list[tuple[str, int]]:
        """Per-namespace gallery counts for the tag browser pills."""
        rows = await self.session.execute(
            select(Tag.namespace, func.count(GalleryTag.gallery_id.distinct()))
            .join(GalleryTag, GalleryTag.tag_id == Tag.id)
            .join(Gallery, Gallery.id == GalleryTag.gallery_id)
            .where(Gallery.expunged.is_(False), Gallery.trashed.is_(False))
            .group_by(Tag.namespace)
        )
        return [(namespace, int(count)) for namespace, count in rows]

    async def tags_for_galleries(
        self, gallery_ids: Sequence[int], limit_per_gallery: int = 4
    ) -> dict[int, list[tuple[str, str]]]:
        """Tags for a set of galleries in one query, ordered per gallery."""
        if not gallery_ids:
            return {}
        rows = await self.session.execute(
            select(GalleryTag.gallery_id, Tag.namespace, Tag.name)
            .join(Tag, Tag.id == GalleryTag.tag_id)
            .where(GalleryTag.gallery_id.in_(list(gallery_ids)))
            .order_by(GalleryTag.gallery_id, Tag.namespace, Tag.name)
        )
        result: dict[int, list[tuple[str, str]]] = {}
        for gallery_id, namespace, name in rows:
            tags = result.setdefault(gallery_id, [])
            if len(tags) < limit_per_gallery:
                tags.append((namespace, name))
        return result

    async def tag_counts_for(
        self, pairs: Sequence[tuple[str, str]]
    ) -> list[tuple[str, str, int]]:
        """Usage counts for a specific list of (namespace, name) pairs."""
        if not pairs:
            return []
        conds = [tuple_(Tag.namespace, Tag.name) == pair for pair in pairs]
        rows = await self.session.execute(
            select(Tag.namespace, Tag.name, func.count(Gallery.id))
            .select_from(Tag)
            .join(GalleryTag, GalleryTag.tag_id == Tag.id)
            .join(
                Gallery, and_(Gallery.id == GalleryTag.gallery_id, Gallery.expunged.is_(False))
            )
            .where(or_(*conds))
            .group_by(Tag.id)
        )
        return [(ns, name, int(count)) for ns, name, count in rows]

    async def random_id(self) -> int | None:
        return await self.session.scalar(
            select(Gallery.id)
            .where(Gallery.expunged.is_(False), Gallery.trashed.is_(False))
            .order_by(func.random())
            .limit(1)
        )

    async def list_trashed(self, page: int, page_size: int) -> tuple[int, list[Gallery]]:
        query = select(Gallery).where(Gallery.trashed.is_(True))
        total = int(await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows = (
            await self.session.scalars(
                query.order_by(Gallery.trashed_at.desc().nullslast(), Gallery.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return total, list(rows)

    async def list_expunged(self, page: int, page_size: int) -> tuple[int, list[Gallery]]:
        query = select(Gallery).where(Gallery.expunged.is_(True), Gallery.trashed.is_(False))
        total = int(await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows = (
            await self.session.scalars(
                query.order_by(Gallery.updated_at.desc(), Gallery.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return total, list(rows)

    async def list_integrity_issues(self, page: int, page_size: int) -> tuple[int, list[Gallery]]:
        # Page count vs actual gallery_pages rows, excluding trashed/expunged and intentional truncations
        page_count_sub = (
            select(GalleryPage.gallery_id, func.count(GalleryPage.id).label("cnt"))
            .group_by(GalleryPage.gallery_id)
            .subquery()
        )
        from ..models import DownloadTask

        trunc_exists = (
            select(1)
            .select_from(DownloadTask)
            .where(DownloadTask.gid == Gallery.gid, DownloadTask.max_pages == Gallery.page_count)
            .exists()
        )
        query = (
            select(Gallery)
            .outerjoin(page_count_sub, page_count_sub.c.gallery_id == Gallery.id)
            .where(Gallery.trashed.is_(False), Gallery.expunged.is_(False))
            .where(Gallery.page_count.is_not(None))
            .where(Gallery.page_count != func.coalesce(page_count_sub.c.cnt, 0))
            .where(~trunc_exists)
        )
        total = int(await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows = (
            await self.session.scalars(
                query.order_by(Gallery.id.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        return total, list(rows)

    async def restore_galleries(self, ids: list[int]) -> int:
        if not ids:
            return 0
        result = await self.session.execute(
            update(Gallery)
            .where(Gallery.id.in_(ids))
            .values(trashed=False, trashed_at=None, expunged=False, updated_at=datetime.now(UTC))
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def purge_galleries(self, ids: list[int]) -> int:
        if not ids:
            return 0
        # Hard delete trashed/expunged rows (also delete pages/tags via cascade)
        rows = await self.session.scalars(select(Gallery).where(Gallery.id.in_(ids)))
        count = 0
        for row in rows:
            await self.session.delete(row)
            count += 1
        await self.session.flush()
        return count

    async def progress(self, gallery_id: int) -> ReadingProgress | None:
        return await self.session.get(ReadingProgress, gallery_id)

    async def upsert_progress(
        self, gallery_id: int, current_page: int, total_pages: int | None
    ) -> ReadingProgress:
        row = await self.session.get(ReadingProgress, gallery_id)
        if row is None:
            row = ReadingProgress(
                gallery_id=gallery_id, current_page=current_page, total_pages=total_pages
            )
            self.session.add(row)
        else:
            row.current_page, row.total_pages, row.updated_at = (
                current_page,
                total_pages,
                datetime.now(UTC),
            )
        await self.session.flush()
        return row

    async def record_history(
        self, gallery_id: int, current_page: int, total_pages: int | None
    ) -> ReadingHistory:
        row = await self.session.scalar(
            select(ReadingHistory).where(ReadingHistory.gallery_id == gallery_id)
        )
        if row is None:
            row = ReadingHistory(
                gallery_id=gallery_id, current_page=current_page, total_pages=total_pages
            )
            self.session.add(row)
        else:
            row.current_page, row.total_pages, row.last_read_at = (
                current_page,
                total_pages,
                datetime.now(UTC),
            )
        await self.session.flush()
        return row

    async def history_page(self, page: int, page_size: int) -> tuple[int, list[ReadingHistory]]:
        query = select(ReadingHistory)
        total = int(
            await self.session.scalar(select(func.count()).select_from(ReadingHistory)) or 0
        )
        rows = (
            await self.session.scalars(
                query.order_by(ReadingHistory.last_read_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return total, list(rows)

    async def clear_history(self) -> None:
        await self.session.execute(delete(ReadingHistory))

    async def clear_progress(self) -> None:
        await self.session.execute(delete(ReadingProgress))

    async def delete_progress(self, gallery_id: int) -> bool:
        row = await self.session.get(ReadingProgress, gallery_id)
        if row is not None:
            await self.session.delete(row)
            return True
        return False

    async def get(self, gid: int) -> tuple[Gallery, list[GalleryPage]] | None:
        model = await self.session.scalar(select(Gallery).where(Gallery.gid == gid))
        if model is None:
            return None
        pages = (
            await self.session.scalars(
                select(GalleryPage)
                .where(GalleryPage.gallery_id == model.id)
                .order_by(GalleryPage.page_index)
            )
        ).all()
        return model, list(pages)

    async def get_for_tag_sync(self, identifier: int) -> Gallery | None:
        # Two-pass lookup: ``or_`` + ``scalar_one_or_none`` raises
        # MultipleResultsFound when one gallery's id equals another's gid.
        row = await self.session.scalar(select(Gallery).where(Gallery.id == identifier))
        if row is not None:
            return row
        return await self.session.scalar(select(Gallery).where(Gallery.gid == identifier))

    async def mark_tag_not_visible(self, gallery_id: int) -> None:
        """Suspend tag sync for a gallery the current site cannot see.

        Used when the public E-Hentai mirror reports an ExHentai-only gallery
        as not found: unlike :meth:`mark_tag_synced` with ``deleted`` this does
        NOT reclassify the gallery — the 404 is a permission/site artefact, not
        a deletion. ``tags_synced_at`` is stamped so it leaves the pending
        queue, and ``source_meta.eh_not_visible`` records the reason so a later
        switch back to ExHentai can resume it (see :meth:`resume_not_visible`).
        """
        row = await self.session.get(Gallery, gallery_id)
        if row is not None:
            row.tags_synced_at = datetime.now(UTC)
            row.category_refreshed_at = datetime.now(UTC)
            meta = dict(row.source_meta or {})
            meta["eh_not_visible"] = True
            row.source_meta = meta
        await self.session.flush()

    async def resume_not_visible(self) -> int:
        """Re-queue every gallery suspended for being not-visible on E-Hentai.

        Clearing ``tags_synced_at`` puts them back on the tag-sync pending
        queue (the worker reseeds on the next tick); the marker is dropped so a
        later public-mirror trip cannot re-suspend a synced gallery. Returns
        the number of galleries resumed.
        """
        result = await self.session.execute(
            update(Gallery)
            .where(Gallery.source_meta.has_key("eh_not_visible"))
            .values(
                tags_synced_at=None,
                category_refreshed_at=None,
                source_meta=Gallery.source_meta.op("-")("eh_not_visible"),
            )
        )
        return int(result.rowcount or 0)

    async def mark_tag_synced(self, gallery_id: int, category: str | None = None) -> None:
        """Mark a gallery's tags as synchronized without writing any tags.

        Used for galleries that no longer exist on ExHentai (404): there is
        nothing to sync, so we timestamp them to keep them out of the pending
        queue instead of failing forever.  When ``category`` is given (e.g.
        ``deleted``) the gallery is reclassified into that category too.
        """
        row = await self.session.get(Gallery, gallery_id)
        if row is not None:
            row.tags_synced_at = datetime.now(UTC)
            row.category_refreshed_at = datetime.now(UTC)
            if category:
                row.category = category
        await self.session.flush()

    async def repair_deleted_misclassified(self, gids: list[int] | None = None) -> int:
        """Requeue galleries mis-marked as ``deleted`` that are not expunged.

        Clears ``tags_synced_at``/``category_refreshed_at`` and restores
        ``category`` from ``gallery_metadata`` when it says the gallery is
        still alive (``expunged=false``) or when no explicit deleted verdict
        exists.  If ``gids`` is given only those gids are considered;
        otherwise every ``deleted`` row is checked.  Returns repaired count.
        """
        # Build base filter: deleted, not expunged, has gid
        filt = [Gallery.category == "deleted", Gallery.expunged.is_(False), Gallery.gid.is_not(None)]
        if gids:
            filt.append(Gallery.gid.in_(list(dict.fromkeys(gids))))
        result = await self.session.execute(select(Gallery).where(and_(*filt)))
        rows = list(result.scalars().all())
        if not rows:
            return 0
        # Fetch metadata verdicts for these gids
        gid_list = [int(r.gid) for r in rows if r.gid is not None]
        meta_map = await self.metadata_map(gid_list)
        repaired = 0
        for row in rows:
            gid = int(row.gid) if row.gid is not None else None
            meta = meta_map.get(gid) if gid is not None else None
            # If metadata says expunged=true, keep deleted (true positive)
            if meta is not None and meta.get("expunged"):
                continue
            # Otherwise restore: prefer metadata category, else "other" to
            # trigger category backfill
            new_cat = None
            if meta and meta.get("category") and meta.get("category") != "deleted":
                new_cat = meta["category"]
            elif meta is None:
                new_cat = "other"
            else:
                # meta exists but category is deleted/missing — let backfill fix
                new_cat = "other"
            row.category = new_cat
            row.tags_synced_at = None
            row.category_refreshed_at = None
            repaired += 1
        await self.session.flush()
        return repaired

    async def refresh_category(self, gallery_id: int, category: str) -> None:
        """Update a gallery's category in place (used by category backfill)."""
        row = await self.session.get(Gallery, gallery_id)
        if row is not None and category and category != "other":
            row.category = category
        if row is not None:
            row.category_refreshed_at = datetime.now(UTC)
        await self.session.flush()

    async def pending_category_refresh_ids(
        self, limit: int = 500, last_id: int = 0
    ) -> list[int]:
        """Gallery ids still in the generic 'other' bucket despite having tags.

        These are galleries that were tag-synced before category refresh existed,
        so their real 大分类 was never written back.  They are re-fetched (once)
        to correct the category.
        """
        rows = await self.session.execute(
            select(Gallery.id)
            .where(
                Gallery.id > last_id,
                Gallery.gid.is_not(None),
                Gallery.token.is_not(None),
                Gallery.category == "other",
                Gallery.tags_synced_at.is_not(None),
                Gallery.category_refreshed_at.is_(None),
            )
            .order_by(Gallery.id)
            .limit(limit)
        )
        return [int(row[0]) for row in rows]

    async def count_pending_category_refresh(self) -> int:
        rows = await self.session.scalar(
            select(func.count(Gallery.id)).where(
                Gallery.gid.is_not(None),
                Gallery.token.is_not(None),
                Gallery.category == "other",
                Gallery.tags_synced_at.is_not(None),
                Gallery.category_refreshed_at.is_(None),
            )
        )
        return int(rows or 0)

    async def get_by_identifier(self, identifier: int) -> Gallery | None:
        """Fetch a gallery by ``id`` or ``gid`` without deleting it."""
        # Two-pass lookup: ``or_`` + ``scalar_one_or_none`` raises
        # MultipleResultsFound when one gallery's id equals another's gid.
        row = await self.session.scalar(select(Gallery).where(Gallery.id == identifier))
        if row is not None:
            return row
        return await self.session.scalar(select(Gallery).where(Gallery.gid == identifier))

    async def delete_ids(self, ids: list[int]) -> int:
        """Bulk delete galleries by primary key; returns the number removed."""
        if not ids:
            return 0
        rows = await self.session.scalars(select(Gallery).where(Gallery.id.in_(ids)))
        models = list(rows)
        for model in models:
            await self.session.delete(model)
        await self.session.flush()
        return len(models)

    async def upsert_metadata(self, entries: list[dict]) -> int:
        """Bulk upsert cached gdata metadata into ``gallery_metadata``.

        ``entries`` is the shape returned by ``EhClient.fetch_gmetadata`` keyed
        by gid; returns the number of rows written.
        """
        if not entries:
            return 0
        now = datetime.now(UTC)
        rows = []
        for e in entries:
            posted = e.get("posted")
            tags = [
                (parts if len(parts := value.split(":", 1)) == 2 else ["misc", value])
                for value in (e.get("tags") or [])
                if value
            ]
            posted_at = None
            if posted:
                try:
                    posted_at = datetime.fromtimestamp(int(posted), tz=UTC)
                except (ValueError, OSError, OverflowError, TypeError):
                    posted_at = None
            rows.append(
                {
                    "gid": int(e["gid"]),
                    "token": e.get("token") or None,
                    "title": e.get("title") or None,
                    "title_jpn": e.get("title_jpn") or None,
                    "category": (
                        normalize_category(e.get("category"))
                        if e.get("category")
                        else None
                    ),
                    "uploader": e.get("uploader") or None,
                    "file_count": e.get("file_count"),
                    "file_size": e.get("file_size"),
                    "rating": e.get("rating"),
                    "posted_at": posted_at,
                    "expunged": bool(e.get("expunged")),
                    "tags": tags,
                    "updated_at": now,
                }
            )
        batch_size = 500
        written = 0
        for start in range(0, len(rows), batch_size):
            statement = pg_insert(GalleryMetadata).values(rows[start : start + batch_size])
            statement = statement.on_conflict_do_update(
                index_elements=["gid"],
                set_={
                    "token": statement.excluded.token,
                    "title": statement.excluded.title,
                    "title_jpn": statement.excluded.title_jpn,
                    "category": statement.excluded.category,
                    "uploader": statement.excluded.uploader,
                    "file_count": statement.excluded.file_count,
                    "file_size": statement.excluded.file_size,
                    "rating": statement.excluded.rating,
                    "posted_at": statement.excluded.posted_at,
                    "expunged": statement.excluded.expunged,
                    "tags": statement.excluded.tags,
                    "updated_at": statement.excluded.updated_at,
                },
                # Only advance updated_at when the content actually changed, so a
                # later metadata-apply pass can tell "fresh" from "same as last
                # time" without rewriting local galleries every check.
                where=or_(
                    GalleryMetadata.tags.is_distinct_from(statement.excluded.tags),
                    GalleryMetadata.category.is_distinct_from(statement.excluded.category),
                    GalleryMetadata.title.is_distinct_from(statement.excluded.title),
                    GalleryMetadata.title_jpn.is_distinct_from(statement.excluded.title_jpn),
                    GalleryMetadata.posted_at.is_distinct_from(statement.excluded.posted_at),
                    GalleryMetadata.file_size.is_distinct_from(statement.excluded.file_size),
                    GalleryMetadata.file_count.is_distinct_from(statement.excluded.file_count),
                    GalleryMetadata.rating.is_distinct_from(statement.excluded.rating),
                ),
            )
            result = await self.session.execute(statement)
            written += result.rowcount or 0
        return written

    async def metadata_map(self, gids: list[int]) -> dict[int, dict]:
        """Return cached gdata metadata for gids, ``{gid: {…}}`` with parsed tags."""
        if not gids:
            return {}
        result: dict[int, dict] = {}
        for chunk in _chunked(list(dict.fromkeys(gids))):
            rows = await self.session.scalars(
                select(GalleryMetadata).where(GalleryMetadata.gid.in_(chunk))
            )
            for row in rows:
                tags = [
                    {"namespace": str(pair[0] or "misc"), "name": str(pair[1])}
                    for pair in (row.tags or [])
                    if len(pair) == 2 and str(pair[1]).strip()
                ]
                result[int(row.gid)] = {
                    "token": row.token,
                    "title": row.title,
                    "title_jpn": row.title_jpn,
                    "category": row.category,
                    "uploader": row.uploader,
                    "file_count": row.file_count,
                    "file_size": row.file_size,
                    "rating": row.rating,
                    "posted_at": row.posted_at,
                    "expunged": row.expunged,
                    "tags": tags,
                }
        return result

    async def metadata_for_gid(self, gid: int) -> dict | None:
        return (await self.metadata_map([gid])).get(gid)

    async def seed_metadata_from_galleries(self, favcat: int) -> int:
        """Backfill the metadata cache from on-disk galleries for a folder.

        Galleries already local already carry title/tags/category/posted, so
        filling the cache from ``galleries`` avoids a network fetch for them.
        Returns the number of rows seeded.
        """
        statement = pg_insert(GalleryMetadata).from_select(
            [
                "gid",
                "token",
                "title",
                "title_jpn",
                "category",
                "uploader",
                "file_count",
                "file_size",
                "rating",
                "posted_at",
                "expunged",
                "tags",
                "updated_at",
            ],
            select(
                Gallery.gid,
                Gallery.token,
                Gallery.title,
                Gallery.title_jpn,
                Gallery.category,
                Gallery.uploader,
                Gallery.file_count,
                Gallery.file_size,
                Gallery.rating,
                Gallery.posted_at,
                Gallery.expunged,
                select(func.jsonb_agg(func.jsonb_build_array(Tag.namespace, Tag.name)))
                .select_from(GalleryTag)
                .join(Tag, Tag.id == GalleryTag.tag_id)
                .where(GalleryTag.gallery_id == Gallery.id)
                .correlate(Gallery)
                .scalar_subquery(),
                func.now(),
            )
            .select_from(FavoriteItem)
            .join(Gallery, Gallery.gid == FavoriteItem.gid)
            .where(
                FavoriteItem.favcat == favcat,
                Gallery.gid.is_not(None),
                ~select(GalleryMetadata.gid)
                .where(GalleryMetadata.gid == Gallery.gid)
                .exists(),
            ),
        )
        statement = statement.on_conflict_do_nothing(index_elements=["gid"])
        result = await self.session.execute(statement)
        return result.rowcount or 0

    async def cold_metadata_gids(self, favcat: int, limit: int = 500) -> list[tuple[int, str]]:
        """``(gid, token)`` for folder galleries missing from the metadata cache."""
        rows = await self.session.execute(
            select(FavoriteItem.gid, FavoriteItem.token)
            .select_from(FavoriteItem)
            .outerjoin(GalleryMetadata, GalleryMetadata.gid == FavoriteItem.gid)
            .where(FavoriteItem.favcat == favcat, GalleryMetadata.gid.is_(None))
            .limit(limit)
        )
        return [(int(row[0]), str(row[1])) for row in rows]

    async def pending_image_quality_gids(
        self, limit: int = 500, last_id: int = 0
    ) -> list[Gallery]:
        """Local galleries whose image quality is still unknown.

        Filters to galleries that could ever be inferred: a known ExHentai
        ``gid``, a token for gdata lookups, a real on-disk ``storage_size`` and
        not expunged.  Oldest-first, id-cursor paged for bounded memory.
        """
        return list(
            (
                await self.session.scalars(
                    select(Gallery)
                    .where(
                        Gallery.gid.is_not(None),
                        Gallery.image_quality.is_(None),
                        Gallery.expunged.is_(False),
                        Gallery.token.is_not(None),
                        Gallery.storage_size.is_not(None),
                        Gallery.storage_size > 0,
                        Gallery.id > last_id,
                    )
                    .order_by(Gallery.id)
                    .limit(limit)
                )
            ).all()
        )

    async def storage_size_map(
        self, gids: list[int]
    ) -> dict[int, tuple[int | None, str | None]]:
        """``gid -> (local storage_size, storage_type)`` for on-disk galleries."""
        if not gids:
            return {}
        rows = await self.session.execute(
            select(Gallery.gid, Gallery.storage_size, Gallery.storage_type).where(
                Gallery.gid.in_(list(dict.fromkeys(gids)))
            )
        )
        return {int(gid): (size, stype) for gid, size, stype in rows}

    async def set_image_qualities(self, mapping: dict[int, str]) -> int:
        """Persist inferred image quality per gid (never overwrites known ones).

        Only rows whose quality is still ``NULL`` are touched, so a download
        that explicitly marked a gallery keeps its authoritative value.
        """
        if not mapping:
            return 0
        stmt = (
            update(Gallery)
            .where(
                Gallery.gid.in_(list(mapping.keys())),
                Gallery.image_quality.is_(None),
            )
            .values(
                image_quality=case(
                    *[(Gallery.gid == gid, quality) for gid, quality in mapping.items()],
                    else_=Gallery.image_quality,
                ),
                updated_at=datetime.now(UTC),
            )
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def apply_metadata_to_galleries(self, favcat: int, limit: int = 200) -> int:
        """Apply fresh cached metadata to local galleries of a favorite folder.

        For every on-disk gallery in the folder whose metadata cache is newer
        than its last tag sync, updates tags (replacing ``gallery_tags``),
        category, title, title_jpn, posted_at, file_size, file_count, rating,
        uploader and stamps ``tags_synced_at``.  Returns the number processed.
        """
        rows = await self.session.execute(
            select(Gallery, GalleryMetadata)
            .select_from(FavoriteItem)
            .join(Gallery, Gallery.gid == FavoriteItem.gid)
            .join(GalleryMetadata, GalleryMetadata.gid == Gallery.gid)
            .where(
                FavoriteItem.favcat == favcat,
                Gallery.expunged.is_(False),
                or_(
                    Gallery.tags_synced_at.is_(None),
                    GalleryMetadata.updated_at > Gallery.tags_synced_at,
                ),
            )
            .limit(limit)
        )
        pairs = [(gallery, meta) for gallery, meta in rows]
        if not pairs:
            return 0
        now = datetime.now(UTC)
        tag_keys: set[tuple[str, str]] = set()
        # Only galleries whose cached metadata actually carries tags get their
        # tags replaced; an empty tags list (stale/partial gdata response)
        # must not wipe out the already-synced local tags.
        tag_gallery_ids: list[int] = []
        for gallery, meta in pairs:
            gallery.category = meta.category or gallery.category
            gallery.title = meta.title or gallery.title
            gallery.title_jpn = meta.title_jpn or gallery.title_jpn
            gallery.uploader = meta.uploader or gallery.uploader
            gallery.file_count = meta.file_count or gallery.file_count
            gallery.file_size = meta.file_size or gallery.file_size
            gallery.rating = meta.rating or gallery.rating
            gallery.posted_at = meta.posted_at or gallery.posted_at
            gallery.tags_synced_at = now
            meta_tags = meta.tags or []
            if meta_tags:
                tag_gallery_ids.append(gallery.id)
                for tag in meta_tags:
                    namespace = str(tag[0] or "misc").strip() or "misc"
                    name = str(tag[1] or "").strip()
                    if name:
                        tag_keys.add((namespace, name))
        await self.session.flush()
        if tag_gallery_ids:
            await self.session.execute(
                delete(GalleryTag).where(GalleryTag.gallery_id.in_(tag_gallery_ids))
            )
        if tag_keys:
            tag_rows = list(
                (
                    await self.session.scalars(
                        select(Tag).where(tuple_(Tag.namespace, Tag.name).in_(tag_keys))
                    )
                ).all()
            )
            tag_map = {(tag.namespace, tag.name): tag for tag in tag_rows}
            missing = [
                Tag(namespace=ns, name=name) for ns, name in tag_keys if (ns, name) not in tag_map
            ]
            if missing:
                await self.session.execute(
                    pg_insert(Tag)
                    .values([{"namespace": tag.namespace, "name": tag.name} for tag in missing])
                    .on_conflict_do_nothing(index_elements=["namespace", "name"])
                )
                tag_rows = list(
                    (
                        await self.session.scalars(
                            select(Tag).where(tuple_(Tag.namespace, Tag.name).in_(tag_keys))
                        )
                    ).all()
                )
                tag_map = {(tag.namespace, tag.name): tag for tag in tag_rows}
            gallery_tag_rows = [
                {
                    "gallery_id": gallery.id,
                    "tag_id": tag_map[key].id,
                }
                for gallery, meta in pairs
                for key in {
                    (
                        str(tag[0] or "misc").strip() or "misc",
                        str(tag[1] or "").strip(),
                    )
                    for tag in meta.tags or []
                    if str(tag[1] or "").strip()
                }
                if key in tag_map
            ]
            if gallery_tag_rows:
                await self.session.execute(
                    pg_insert(GalleryTag)
                    .values(gallery_tag_rows)
                    .on_conflict_do_nothing(index_elements=["gallery_id", "tag_id"])
                )
        return len(pairs)

    async def replace_tags(
        self,
        gallery: Gallery,
        tags: list[dict[str, str]],
        synced_at: datetime,
        category: str | None = None,
    ) -> int:
        """Replace one gallery's relations while preserving the global tag dictionary.

        Concurrency-safe: missing tags are inserted with ``ON CONFLICT DO
        NOTHING`` so parallel tag-sync workers can't race on the unique
        ``(namespace, name)`` constraint.
        """
        await self.session.execute(delete(GalleryTag).where(GalleryTag.gallery_id == gallery.id))
        await self.session.flush()
        unique_tags: set[tuple[str, str]] = set()
        for tag_data in tags:
            namespace = str(tag_data.get("namespace", "misc")).strip() or "misc"
            name = str(tag_data.get("name", "")).strip()
            if name:
                unique_tags.add((namespace, name))
        if unique_tags:
            statement = (
                pg_insert(Tag)
                .values(
                    [
                        {"namespace": namespace, "name": name}
                        for namespace, name in sorted(unique_tags)
                    ]
                )
                .on_conflict_do_nothing(index_elements=["namespace", "name"])
            )
            await self.session.execute(statement)
            await self.session.flush()
            existing = (
                await self.session.scalars(
                    select(Tag).where(tuple_(Tag.namespace, Tag.name).in_(unique_tags))
                )
            ).all()
            if existing:
                await self.session.execute(
                    pg_insert(GalleryTag)
                    .values(
                        [
                            {"gallery_id": gallery.id, "tag_id": tag.id}
                            for tag in existing
                        ]
                    )
                    .on_conflict_do_nothing(
                        index_elements=["gallery_id", "tag_id"]
                    )
                )
            await self.session.flush()
        if category and category != "other":
            gallery.category = category
        gallery.tags_synced_at = synced_at
        await self.session.flush()
        return len(unique_tags)

    async def pending_tag_sync_ids(
        self, limit: int = 1000, last_id: int = 0
    ) -> list[int]:
        """Gallery ids with ExHentai coordinates but no synced tags yet.

        Uses keyset pagination (``id > last_id``) so callers advance with the
        last returned id. This stays O(limit) even across hundreds of thousands
        of galleries, unlike OFFSET which re-scans skipped rows.
        """
        rows = await self.session.execute(
            select(Gallery.id)
            .where(
                Gallery.id > last_id,
                Gallery.gid.is_not(None),
                Gallery.token.is_not(None),
                Gallery.tags_synced_at.is_(None),
            )
            .order_by(Gallery.id)
            .limit(limit)
        )
        return [row[0] for row in rows]

    async def tag_sync_status_for_gids(
        self, gids: list[int]
    ) -> dict[int, datetime | None]:
        if not gids:
            return {}
        rows = await self.session.execute(
            select(Gallery.gid, Gallery.tags_synced_at).where(Gallery.gid.in_(gids))
        )
        return {gid: synced_at for gid, synced_at in rows}


