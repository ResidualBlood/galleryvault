import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, delete, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..scanners.base import GalleryMeta, normalize_category
from .models import (
    AppConfig,
    DownloadAttempt,
    DownloadTask,
    DuplicateIgnore,
    FavoriteItem,
    FavoritesMonitor,
    Gallery,
    GalleryMetadata,
    GalleryPage,
    GalleryTag,
    ReadingHistory,
    ReadingProgress,
    Tag,
)


def path_hash(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()


class GalleryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, gallery: GalleryMeta) -> Gallery:
        key = (
            Gallery.gid == gallery.gid
            if gallery.gid is not None
            else Gallery.path_hash == path_hash(gallery.path)
        )
        model = await self.session.scalar(select(Gallery).where(key))
        values = {
            "gid": gallery.gid,
            "token": gallery.token,
            "title": gallery.title,
            "title_jpn": gallery.title_jpn,
            "category": gallery.category,
            "uploader": gallery.uploader,
            "file_count": gallery.file_count,
            "file_size": gallery.file_size,
            "rating": gallery.rating,
            "storage_type": gallery.storage_type,
            "storage_path": str(gallery.path),
            "path_hash": path_hash(gallery.path),
            "storage_mtime_ns": gallery.storage_mtime_ns,
            "storage_size": gallery.storage_size,
            "storage_signature": gallery.storage_signature,
            "expunged": False,
            "cover_path": gallery.pages[0].name if gallery.pages else None,
            "page_count": len(gallery.pages),
            "source_meta": {**gallery.source_meta, "warnings": gallery.warnings},
            "updated_at": datetime.now(UTC),
        }
        if model is None:
            model = Gallery(**values)
            self.session.add(model)
            await self.session.flush()
        else:
            # The scanner signature covers metadata and every image member. Avoid
            # rebuilding relations for an unchanged gallery during full scans.
            if model.storage_signature == gallery.storage_signature and not model.expunged:
                return model
            for name, value in values.items():
                setattr(model, name, value)
            await self.session.flush()

        await self.session.execute(delete(GalleryPage).where(GalleryPage.gallery_id == model.id))
        self.session.add_all(
            [
                GalleryPage(
                    gallery_id=model.id,
                    page_index=page.index,
                    member_name=page.name,
                    media_type=page.media_type,
                    manifest={"size": page.size, "mtime_ns": page.mtime_ns},
                )
                for page in gallery.pages
            ]
        )
        await self.session.execute(delete(GalleryTag).where(GalleryTag.gallery_id == model.id))
        unique_tags = {
            (
                str(item.get("namespace", "misc")).strip() or "misc",
                str(item.get("name", "")).strip(),
            )
            for item in gallery.tags
            if str(item.get("name", "")).strip()
        }
        existing = (
            list(
                (
                    await self.session.scalars(
                        select(Tag).where(tuple_(Tag.namespace, Tag.name).in_(unique_tags))
                    )
                ).all()
            )
            if unique_tags
            else []
        )
        by_name = {(tag.namespace, tag.name): tag for tag in existing}
        missing = [
            Tag(namespace=namespace, name=name)
            for namespace, name in unique_tags
            if (namespace, name) not in by_name
        ]
        self.session.add_all(missing)
        if missing:
            await self.session.flush()
            by_name.update({(tag.namespace, tag.name): tag for tag in missing})
        self.session.add_all(
            [GalleryTag(gallery_id=model.id, tag_id=by_name[key].id) for key in unique_tags]
        )
        await self.session.flush()
        return model

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
        existing = list(
            (
                await self.session.scalars(
                    select(Gallery).where(
                        (Gallery.gid.in_(gids) if gids else False)
                        | (Gallery.path_hash.in_(hashes) if hashes else False)
                    )
                )
            ).all()
        )
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

    async def signatures(self, roots: Sequence[str | Path]) -> dict[str, tuple[str, str]]:
        """Return path hash -> (signature, path) for roots, without scanning page data.

        Streams rows with ``yield_per`` so a library of hundreds of thousands of
        galleries never materialises every ``Gallery`` ORM object at once; only
        the three needed columns are fetched.
        """
        if not roots:
            return {}
        normalized = [str(Path(root).resolve()) for root in roots]
        result = await self.session.stream(
            select(Gallery.path_hash, Gallery.storage_signature, Gallery.storage_path).where(
                Gallery.expunged.is_(False)
            )
        )
        out: dict[str, tuple[str, str]] = {}
        async for row in result:
            storage_path = row._mapping["storage_path"]
            if any(Path(storage_path).resolve().is_relative_to(root) for root in normalized):
                out[row._mapping["path_hash"]] = (row._mapping["storage_signature"], storage_path)
        return out

    async def expunge_missing(self, roots: Sequence[str | Path], seen: set[str]) -> int:
        normalized = [str(Path(root).resolve()) for root in roots]
        result = await self.session.stream(
            select(Gallery.id, Gallery.path_hash, Gallery.storage_path).where(
                Gallery.expunged.is_(False)
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
        tag_mode: str = "or",
        tag_match: str = "exact",
        category: str | None = None,
    ) -> tuple[int, list[Gallery]]:
        query = select(Gallery)
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            query = query.where(Gallery.title.ilike(pattern) | Gallery.title_jpn.ilike(pattern))
        if category:
            query = query.where(Gallery.category == category)
        if tags:
            tag_conditions = []
            for namespace, name in tags:
                pattern = name if tag_match == "exact" else f"%{name}%"
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
        query = query.where(Gallery.expunged.is_(False))
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = (
            await self.session.scalars(
                query.order_by(Gallery.id.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        return total, list(rows)

    async def next_gallery_id(self, current_id: int) -> int | None:
        """The next non-expunged gallery id after ``current_id`` (ascending)."""
        return await self.session.scalar(
            select(Gallery.id)
            .where(Gallery.id > current_id, Gallery.expunged.is_(False))
            .order_by(Gallery.id)
            .limit(1)
        )

    async def search_tags(
        self, q: str | None, page: int, page_size: int, namespace: str | None = None
    ) -> tuple[int, list[tuple[str, str, int]]]:
        pattern = f"%{q.strip()}%" if q and q.strip() else None
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

    async def tag_facets(self) -> list[tuple[str, int]]:
        """Per-namespace gallery counts for the tag browser pills."""
        rows = await self.session.execute(
            select(Tag.namespace, func.count(GalleryTag.gallery_id.distinct()))
            .join(GalleryTag, GalleryTag.tag_id == Tag.id)
            .join(Gallery, Gallery.id == GalleryTag.gallery_id)
            .where(Gallery.expunged.is_(False))
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
            .where(Gallery.expunged.is_(False))
            .order_by(func.random())
            .limit(1)
        )

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
        return await self.session.scalar(
            select(Gallery).where((Gallery.id == identifier) | (Gallery.gid == identifier))
        )

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

    async def delete_by_identifier(self, identifier: int) -> Gallery | None:
        """Remove a gallery (cascading to pages, tags links, progress, history)."""
        model = await self.session.scalar(
            select(Gallery).where((Gallery.id == identifier) | (Gallery.gid == identifier))
        )
        if model is None:
            return None
        await self.session.delete(model)
        await self.session.flush()
        return model

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
        rows = await self.session.scalars(
            select(GalleryMetadata).where(GalleryMetadata.gid.in_(list(dict.fromkeys(gids))))
        )
        result: dict[int, dict] = {}
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
            for tag in meta.tags or []:
                namespace = str(tag[0] or "misc").strip() or "misc"
                name = str(tag[1] or "").strip()
                if name:
                    tag_keys.add((namespace, name))
        await self.session.flush()
        gallery_ids = [gallery.id for gallery, _ in pairs]
        await self.session.execute(
            delete(GalleryTag).where(GalleryTag.gallery_id.in_(gallery_ids))
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
            self.session.add_all(
                GalleryTag(gallery_id=gallery.id, tag_id=tag_map[key].id)
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
            for tag in existing:
                self.session.add(GalleryTag(gallery_id=gallery.id, tag_id=tag.id))
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


class DownloadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        gid: int,
        token: str,
        title: str | None = None,
        mode: str | None = None,
        max_pages: int | None = None,
    ) -> DownloadTask | None:
        active = await self.session.scalar(
            select(DownloadTask).where(
                DownloadTask.gid == gid, DownloadTask.status.in_(["pending", "downloading"])
            )
        )
        if active:
            return None
        task = DownloadTask(
            gid=gid,
            token=token,
            title=title,
            mode=mode,
            status="pending",
            retry_count=0,
            max_retries=3,
            max_pages=max_pages,
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def recover_orphans(self) -> int:
        result = await self.session.execute(
            update(DownloadTask)
            .where(DownloadTask.status == "downloading")
            .values(status="pending", updated_at=datetime.now(UTC))
        )
        return int(result.rowcount or 0)

    async def claim_pending(self) -> DownloadTask | None:
        row = await self.session.scalar(
            select(DownloadTask)
            .where(
                DownloadTask.status == "pending",
                DownloadTask.retry_count < DownloadTask.max_retries,
            )
            .order_by(DownloadTask.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is not None:
            row.status = "downloading"
            row.started_at = datetime.now(UTC)
            row.updated_at = row.started_at
        return row

    async def record_attempt(
        self, task_id: int, attempt: int, status: str, error: str | None = None
    ) -> None:
        self.session.add(
            DownloadAttempt(task_id=task_id, attempt=attempt, status=status, error_message=error)
        )
        await self.session.flush()

    async def progress(self, task_id: int, current_page: int, total_pages: int) -> None:
        row = await self.session.get(DownloadTask, task_id)
        if row is not None:
            row.current_page = current_page
            row.total_pages = total_pages
            row.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def list_page(
        self, page: int, page_size: int, status: str | None = None
    ) -> tuple[int, list[DownloadTask]]:
        query = select(DownloadTask)
        if status:
            query = query.where(DownloadTask.status == status)
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = (
            await self.session.scalars(
                query.order_by(DownloadTask.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return total, list(rows)

    async def cancel(self, task_id: int) -> bool:
        task = await self.session.get(DownloadTask, task_id)
        if task is None:
            return False
        if task.status in {"pending", "downloading"}:
            task.status = "cancelled"
        return True

    async def delete(self, task_id: int) -> bool:
        """Permanently remove a download task (and its attempt log)."""
        task = await self.session.get(DownloadTask, task_id)
        if task is None:
            return False
        await self.session.delete(task)
        return True


class FavoritesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def categories(self) -> list[FavoritesMonitor]:
        return list(
            (
                await self.session.scalars(
                    select(FavoritesMonitor).order_by(FavoritesMonitor.favcat)
                )
            ).all()
        )

    async def counts_and_sizes(self) -> dict[int, tuple[int, int, int]]:
        """Per-favcat stats: (cloud items, local galleries, local bytes).

        ``cloud`` counts every favorite item recorded for the folder; ``local``
        counts the ones present locally (galleries table, not expunged) and
        ``local bytes`` is the sum of their file_size.  The API derives an
        estimated cloud size from these.
        """
        rows = await self.session.execute(
            select(
                FavoriteItem.favcat,
                func.count(FavoriteItem.id),
                func.count(Gallery.id).filter(Gallery.expunged.is_(False)),
                func.coalesce(
                    func.sum(Gallery.file_size).filter(Gallery.expunged.is_(False)), 0
                ),
            )
            .outerjoin(Gallery, Gallery.gid == FavoriteItem.gid)
            .group_by(FavoriteItem.favcat)
        )
        return {int(favcat): (int(cloud), int(local), int(size)) for favcat, cloud, local, size in rows}

    async def cloud_size_breakdown(self, favcat: int) -> tuple[int, int]:
        """Exact-ish cloud size for a folder: ``(known bytes, unknown count)``.

        ``known`` sums local gallery file_size for galleries already on disk and
        the recorded ``favorite_items.file_size`` for the missing ones that have
        been fetched; ``unknown`` counts missing galleries whose size has not
        been fetched yet (the API fills those with the local average).
        """
        row = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(func.coalesce(Gallery.file_size, FavoriteItem.file_size)), 0
                ),
                func.count().filter(
                    and_(Gallery.id.is_(None), FavoriteItem.file_size.is_(None))
                ),
            )
            .select_from(FavoriteItem)
            .outerjoin(
                Gallery,
                and_(Gallery.gid == FavoriteItem.gid, Gallery.expunged.is_(False)),
            )
            .where(FavoriteItem.favcat == favcat)
        )
        result = row.one()
        return int(result[0]), int(result[1])

    async def pending_size_gids(self, favcat: int, limit: int = 200) -> list[tuple[int, str]]:
        """``(gid, token)`` of folder galleries missing a size and not local."""
        rows = await self.session.execute(
            select(FavoriteItem.gid, FavoriteItem.token)
            .select_from(FavoriteItem)
            .outerjoin(
                Gallery,
                and_(Gallery.gid == FavoriteItem.gid, Gallery.expunged.is_(False)),
            )
            .where(
                FavoriteItem.favcat == favcat,
                Gallery.id.is_(None),
                FavoriteItem.file_size.is_(None),
            )
            .limit(limit)
        )
        return [(int(row[0]), str(row[1])) for row in rows]

    async def set_file_size(self, favcat: int, gid: int, size: int | None) -> None:
        await self.session.execute(
            update(FavoriteItem)
            .where(FavoriteItem.favcat == favcat, FavoriteItem.gid == gid)
            .values(file_size=size)
        )

    async def category(self, favcat: int) -> FavoritesMonitor | None:
        return await self.session.scalar(
            select(FavoritesMonitor).where(FavoritesMonitor.favcat == favcat)
        )

    async def known_gids(self, favcat: int) -> set[int]:
        rows = await self.session.scalars(
            select(FavoriteItem.gid).where(FavoriteItem.favcat == favcat)
        )
        return set(rows.all())

    async def existing_gallery_gids(self, gids: list[int]) -> set[int]:
        """gids that already exist in the local library (galleries table).

        Used to skip favorite downloads for galleries that are already on disk
        (e.g. an Ehviewer export mounted under a library root), so they are not
        downloaded a second time into the downloads directory.  Expunged rows
        (directory removed and the scan expired them) count as missing, so the
        favorite monitor re-downloads them.
        """
        if not gids:
            return set()
        rows = await self.session.scalars(
            select(Gallery.gid).where(
                Gallery.gid.is_not(None),
                Gallery.expunged.is_(False),
                Gallery.gid.in_(list(dict.fromkeys(gids))),
            )
        )
        return {int(gid) for gid in rows if gid is not None}

    async def remember(self, favcat: int, item) -> None:
        now = datetime.now(UTC)
        row = await self.session.scalar(
            select(FavoriteItem).where(FavoriteItem.favcat == favcat, FavoriteItem.gid == item.gid)
        )
        if row is None:
            self.session.add(
                FavoriteItem(
                    favcat=favcat,
                    gid=item.gid,
                    token=item.token,
                    title=item.title,
                    url=item.url,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            row.token, row.title, row.url, row.last_seen_at = item.token, item.title, item.url, now
        await self.session.flush()

    async def remember_many(self, favcat: int, items: list[object]) -> None:
        """Bulk upsert favorite items, batched for large folders.

        PostgreSQL/asyncpg cap the number of bound parameters per statement, so
        a folder with thousands of galleries must be inserted in chunks.
        """
        if not items:
            return
        now = datetime.now(UTC)
        batch_size = 500
        for start in range(0, len(items), batch_size):
            chunk = items[start : start + batch_size]
            rows = [
                {
                    "favcat": favcat,
                    "gid": item.gid,
                    "token": item.token,
                    "title": item.title,
                    "url": item.url,
                    "first_seen_at": now,
                    "last_seen_at": now,
                }
                for item in chunk
            ]
            statement = pg_insert(FavoriteItem).values(rows)
            statement = statement.on_conflict_do_update(
                constraint="favorite_items_favcat_gid_key",
                set_={
                    "token": statement.excluded.token,
                    "title": statement.excluded.title,
                    "url": statement.excluded.url,
                    "last_seen_at": statement.excluded.last_seen_at,
                },
            )
            await self.session.execute(statement)

    async def checked(self, favcat: int, success: bool) -> None:
        row = await self.category(favcat)
        if row is None:
            row = FavoritesMonitor(favcat=favcat)
            self.session.add(row)
        row.last_checked_at = datetime.now(UTC)
        if success:
            row.last_success_at = row.last_checked_at
        await self.session.flush()

    async def log_check(
        self, favcat: int, gids: list[int], attempts: int, success: bool, error: str | None = None
    ) -> None:
        from .models import FavoritesCheckLog

        self.session.add(
            FavoritesCheckLog(
                favcat=favcat,
                discovered_gids=gids,
                attempts=attempts,
                success=success,
                error_message=error,
            )
        )
        await self.session.flush()

    async def list_items(
        self, favcat: int, page: int, page_size: int
    ) -> tuple[int, list[tuple[object, object | None]]]:
        """Paginated favorite items for a folder, joined with the local gallery.

        Returns ``(total, [(FavoriteItem, Gallery|None)])``.
        """
        query = (
            select(FavoriteItem, Gallery)
            .outerjoin(Gallery, Gallery.gid == FavoriteItem.gid)
            .where(FavoriteItem.favcat == favcat)
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self.session.execute(
                query.order_by(FavoriteItem.last_seen_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return total, [(row[0], row[1]) for row in rows]

    async def all_items(self) -> list[tuple]:
        """Every recorded favorite item joined with the local gallery.

        Returns ``(favcat, gid, token, title, url, gallery_id, file_size,
        first_seen_at, posted_at)`` where ``file_size`` prefers the on-disk
        gallery's real size and falls back to the recorded favorite size.
        """
        rows = await self.session.execute(
            select(
                FavoriteItem.favcat,
                FavoriteItem.gid,
                FavoriteItem.token,
                FavoriteItem.title,
                FavoriteItem.url,
                Gallery.id,
                func.coalesce(Gallery.file_size, FavoriteItem.file_size),
                FavoriteItem.first_seen_at,
                Gallery.posted_at,
            ).outerjoin(Gallery, Gallery.gid == FavoriteItem.gid)
        )
        return [
            (
                int(r[0]),
                int(r[1]),
                str(r[2]),
                str(r[3]),
                str(r[4]),
                int(r[5]) if r[5] is not None else None,
                int(r[6]) if r[6] is not None else None,
                r[7],
                r[8],
            )
            for r in rows
        ]

    async def tags_for_gallery_ids(
        self, gallery_ids: list[int]
    ) -> dict[int, list[tuple[str, str]]]:
        if not gallery_ids:
            return {}
        rows = await self.session.execute(
            select(GalleryTag.gallery_id, Tag.namespace, Tag.name)
            .join(Tag, Tag.id == GalleryTag.tag_id)
            .where(GalleryTag.gallery_id.in_(list(dict.fromkeys(gallery_ids))))
        )
        result: dict[int, list[tuple[str, str]]] = {}
        for gallery_id, namespace, name in rows:
            result.setdefault(int(gallery_id), []).append((namespace, name))
        return result

    async def remove_gids(self, gids: list[int]) -> int:
        if not gids:
            return 0
        result = await self.session.execute(
            delete(FavoriteItem).where(FavoriteItem.gid.in_(gids))
        )
        return result.rowcount or 0

    async def favcats_for_gid(self, gid: int | None) -> list[int]:
        if gid is None:
            return []
        rows = await self.session.scalars(
            select(FavoriteItem.favcat).where(FavoriteItem.gid == gid)
        )
        return sorted({int(f) for f in rows.all()})

    async def category_names(self, favcats: list[int]) -> dict[int, str]:
        if not favcats:
            return {}
        rows = await self.session.scalars(
            select(FavoritesMonitor).where(FavoritesMonitor.favcat.in_(favcats))
        )
        return {int(r.favcat): r.name or "" for r in rows}

    async def galleries_for_gids(self, gids: list[int]) -> dict[int, int]:
        """Map gid -> local gallery.id for galleries on disk (not expunged)."""
        if not gids:
            return {}
        rows = await self.session.execute(
            select(Gallery.gid, Gallery.id).where(
                Gallery.gid.is_not(None),
                Gallery.expunged.is_(False),
                Gallery.gid.in_(list(dict.fromkeys(gids))),
            )
        )
        return {int(gid): int(gid_local) for gid, gid_local in rows if gid is not None}

    async def gallery_titles_by_gid(self, gids: list[int]) -> dict[int, tuple[str | None, str | None]]:
        """Map gid -> (title, title_jpn) for galleries on disk."""
        if not gids:
            return {}
        rows = await self.session.execute(
            select(Gallery.gid, Gallery.title, Gallery.title_jpn).where(
                Gallery.gid.is_not(None), Gallery.gid.in_(list(dict.fromkeys(gids)))
            )
        )
        return {int(gid): (title, title_jpn) for gid, title, title_jpn in rows if gid is not None}

    async def ignored_duplicate_keys(self) -> set[str]:
        rows = await self.session.scalars(select(DuplicateIgnore.key))
        return set(rows.all())

    async def favorite_items_detail_by_gids(self, gids: list[int]) -> dict[int, dict]:
        """Duplicate-scan style item detail for favorite gids (local-join aware)."""
        if not gids:
            return {}
        rows = (
            await self.session.execute(
                select(FavoriteItem, Gallery)
                .outerjoin(Gallery, Gallery.gid == FavoriteItem.gid)
                .where(FavoriteItem.gid.in_(list(dict.fromkeys(gids))))
            )
        ).all()
        pairs = [(item, gallery) for item, gallery in rows]
        local_ids = [
            int(gallery.id)
            for _, gallery in pairs
            if gallery is not None and gallery.id is not None
        ]
        tag_map: dict[int, list[tuple[str, str]]] = {}
        if local_ids:
            tag_rows = await self.session.execute(
                select(GalleryTag.gallery_id, Tag.namespace, Tag.name)
                .join(Tag, Tag.id == GalleryTag.tag_id)
                .where(GalleryTag.gallery_id.in_(list(dict.fromkeys(local_ids))))
            )
            for gallery_id, namespace, name in tag_rows:
                tag_map.setdefault(int(gallery_id), []).append((namespace, name))
        result: dict[int, dict] = {}
        for item, gallery in pairs:
            if gallery is not None:
                result[int(item.gid)] = {
                    "gid": item.gid,
                    "favcat": item.favcat,
                    "token": item.token,
                    "title": item.title or gallery.title or "",
                    "url": item.url,
                    "gallery_id": gallery.id,
                    "category": gallery.category or "other",
                    "page_count": gallery.page_count or 0,
                    "cover_url": f"/api/galleries/{gallery.id}/thumb/0" if gallery.page_count else None,
                    "file_size": gallery.file_size,
                    "first_seen_at": item.first_seen_at,
                    "posted_at": gallery.posted_at,
                    "tags": [
                        {"namespace": ns, "name": name}
                        for ns, name in tag_map.get(gallery.id, [])
                    ],
                }
            else:
                result[int(item.gid)] = {
                    "gid": item.gid,
                    "favcat": item.favcat,
                    "token": item.token,
                    "title": item.title,
                    "url": item.url,
                    "gallery_id": None,
                    "category": None,
                    "page_count": None,
                    "cover_url": None,
                    "file_size": item.file_size,
                    "first_seen_at": item.first_seen_at,
                    "posted_at": None,
                    "tags": [],
                }
        return result

    async def ignored_duplicates(self) -> list[dict[str, object]]:
        rows = await self.session.scalars(
            select(DuplicateIgnore).order_by(DuplicateIgnore.created_at.desc())
        )
        return [
            {
                "key": row.key,
                "title": row.title,
                "gids": row.gids or [],
            }
            for row in rows
        ]

    async def add_duplicate_ignore(
        self, key: str, title: str | None, gids: list[int]
    ) -> None:
        self.session.add(
            DuplicateIgnore(
                key=key,
                title=title or None,
                gids=gids or None,
            )
        )

    async def remove_duplicate_ignore(self, key: str) -> None:
        row = await self.session.get(DuplicateIgnore, key)
        if row is not None:
            await self.session.delete(row)

    async def update_posted_at(self, gid_to_posted: dict[int, datetime]) -> None:
        """Persist ExHentai posted timestamps onto on-disk galleries."""
        if not gid_to_posted:
            return
        for gid, posted in gid_to_posted.items():
            await self.session.execute(
                update(Gallery)
                .where(Gallery.gid.is_not(None), Gallery.gid == gid)
                .values(posted_at=posted)
            )


class SettingsRepository:
    """Persistence for user-editable settings kept outside environment secrets."""

    KEY = "user_settings"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self) -> dict:
        row = await self.session.get(AppConfig, self.KEY)
        return dict(row.value) if row else {}

    async def save(self, value: dict) -> None:
        row = await self.session.get(AppConfig, self.KEY)
        if row is None:
            self.session.add(AppConfig(key=self.KEY, value=value))
        else:
            row.value = value
        await self.session.flush()

    async def save_extra(self, value: dict) -> None:
        """Persist non-editable runtime settings (e.g. a changed password hash).

        These are stored under their own key so they are never written to the
        config file and never show up in the editable settings payload.  The
        existing dict (which also holds ``auth_secret``) is merged, never
        replaced, so a password change does not invalidate session secrets.
        """
        row = await self.session.get(AppConfig, "runtime_auth")
        if row is None:
            self.session.add(AppConfig(key="runtime_auth", value=value))
        else:
            merged = dict(row.value or {})
            merged.update(value)
            row.value = merged
        await self.session.flush()
