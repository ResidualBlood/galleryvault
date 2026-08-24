import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, delete, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..scanners.base import GalleryMeta
from .models import (
    AppConfig,
    DownloadAttempt,
    DownloadTask,
    FavoriteItem,
    FavoritesMonitor,
    Gallery,
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

    async def search_tags(
        self, q: str | None, page: int, page_size: int, namespace: str | None = None
    ) -> tuple[int, list[tuple[str, str, int]]]:
        pattern = f"%{q.strip()}%" if q and q.strip() else None
        query = (
            select(Tag.namespace, Tag.name, func.count(Gallery.id))
            .select_from(Tag)
            .outerjoin(GalleryTag, GalleryTag.tag_id == Tag.id)
            .outerjoin(
                Gallery, and_(Gallery.id == GalleryTag.gallery_id, Gallery.expunged.is_(False))
            )
        )
        if namespace:
            query = query.where(Tag.namespace == namespace)
        if pattern:
            query = query.where(Tag.name.ilike(pattern) | Tag.namespace.ilike(pattern))
        query = query.group_by(Tag.id).order_by(Tag.namespace, Tag.name)
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = (
            await self.session.execute(query.offset((page - 1) * page_size).limit(page_size))
        ).all()
        return total, [(namespace, name, int(count)) for namespace, name, count in rows]

    async def tag_facets(self) -> list[tuple[str, int]]:
        """Per-namespace gallery counts for the tag browser pills."""
        rows = await self.session.execute(
            select(Tag.namespace, func.count(GalleryTag.gallery_id.distinct()))
            .join(GalleryTag, GalleryTag.tag_id == Tag.id)
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
        self, gid: int, token: str, title: str | None = None, mode: str | None = None
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

    async def category(self, favcat: int) -> FavoritesMonitor | None:
        return await self.session.scalar(
            select(FavoritesMonitor).where(FavoritesMonitor.favcat == favcat)
        )

    async def known_gids(self, favcat: int) -> set[int]:
        rows = await self.session.scalars(
            select(FavoriteItem.gid).where(FavoriteItem.favcat == favcat)
        )
        return set(rows.all())

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
        config file and never show up in the editable settings payload.
        """
        row = await self.session.get(AppConfig, "runtime_auth")
        if row is None:
            self.session.add(AppConfig(key="runtime_auth", value=value))
        else:
            row.value = value
        await self.session.flush()
