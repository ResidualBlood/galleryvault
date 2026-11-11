import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, case, delete, false, func, null, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ...scanners.base import ExistingGallery, GalleryMeta, normalize_category
from ..models import (
    DuplicateRecord,
    FavoriteItem,
    Gallery,
    GalleryMetadata,
    GalleryPage,
    GalleryTag,
    LocalListItem,
    Tag,
)
from .base import BaseRepository, _chunked, path_hash
from .galleries_common import (  # noqa: F401
    _IMAGE_MAGIC_PREFIXES,
    _TITLE_SORT_COL_CACHE,
    _dialect_insert,
    _is_valid_page_header,
    _session_dialect,
    _title_sort_column,
    _upsert_uploader_tag,
)
from .galleries_progress import GalleryProgressMixin
from .galleries_query import GalleryQueryMixin


class GalleryRepository(GalleryQueryMixin, GalleryProgressMixin, BaseRepository[Gallery]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Gallery)

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
        existing_by_gid: dict[int, Gallery] = {}
        existing_by_path: dict[str, Gallery] = {}
        for row in existing:
            if row.gid is not None:
                existing_by_gid[row.gid] = row
            if row.path_hash:
                existing_by_path[row.path_hash] = row

        changed: list[tuple[Gallery, GalleryMeta]] = []
        for key, gallery in unique.items():
            p_hash = path_hash(gallery.path)
            row: Gallery | None = None
            if gallery.gid is not None:
                row = existing_by_gid.get(gallery.gid)
            if row is None and p_hash:
                row = existing_by_path.get(p_hash)

            if row is None:
                row = Gallery(**values_by_key[key])
                self.session.add(row)
                if row.gid is not None:
                    existing_by_gid[row.gid] = row
                if row.path_hash:
                    existing_by_path[row.path_hash] = row
                changed.append((row, gallery))
            elif (
                row.storage_signature != gallery.storage_signature
                or row.expunged
                or (gallery.gid is not None and row.gid != gallery.gid)
                or row.path_hash != p_hash
            ):
                for name, value in values_by_key[key].items():
                    if name == "image_quality" and value is None:
                        # Keep an already-known quality: a re-scan of a download
                        # without a fresh quality marker must not erase it.
                        continue
                    if name in ("gid", "token") and value is None and getattr(row, name) is not None:
                        # Keep already-known gid/token if scanner re-scan has no metadata
                        continue
                    setattr(row, name, value)
                if row.gid is not None:
                    existing_by_gid[row.gid] = row
                if row.path_hash:
                    existing_by_path[row.path_hash] = row
                changed.append((row, gallery))
        if changed:
            await self.session.flush()
        if not changed:
            return
        changed_ids = [row.id for row, _ in changed]

        # 1. GalleryPage diff update: compare existing vs desired
        existing_pages = list(
            (
                await self.session.scalars(
                    select(GalleryPage).where(GalleryPage.gallery_id.in_(changed_ids))
                )
            ).all()
        )
        existing_pages_by_key = {
            (p.gallery_id, p.page_index): p for p in existing_pages
        }

        pages_to_add: list[GalleryPage] = []
        page_ids_to_delete: list[int] = []
        desired_page_keys: set[tuple[int, int]] = set()

        for row, gallery in changed:
            for page in gallery.pages:
                k = (row.id, page.index)
                desired_page_keys.add(k)
                existing_page = existing_pages_by_key.get(k)
                manifest_val = {"size": page.size, "mtime_ns": page.mtime_ns}
                if existing_page is None:
                    pages_to_add.append(
                        GalleryPage(
                            gallery_id=row.id,
                            page_index=page.index,
                            member_name=page.name,
                            media_type=page.media_type,
                            manifest=manifest_val,
                        )
                    )
                else:
                    if existing_page.member_name != page.name:
                        existing_page.member_name = page.name
                    if existing_page.media_type != page.media_type:
                        existing_page.media_type = page.media_type
                    if existing_page.manifest != manifest_val:
                        existing_page.manifest = manifest_val

        for p in existing_pages:
            if (p.gallery_id, p.page_index) not in desired_page_keys:
                page_ids_to_delete.append(p.id)

        if page_ids_to_delete:
            await self.session.execute(
                delete(GalleryPage).where(GalleryPage.id.in_(page_ids_to_delete))
            )
        if pages_to_add:
            self.session.add_all(pages_to_add)

        # 2. Tag mapping and GalleryTag diff update
        tag_keys: set[tuple[str, str]] = set()
        for _, gallery in changed:
            tag_keys.update(
                (
                    str(item.get("namespace", "misc")).strip() or "misc",
                    str(item.get("name", "")).strip(),
                )
                for item in gallery.tags
                if str(item.get("name", "")).strip()
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

            existing_gallery_tags = list(
                (
                    await self.session.scalars(
                        select(GalleryTag).where(GalleryTag.gallery_id.in_(changed_ids))
                    )
                ).all()
            )
            existing_tag_pairs = {(gt.gallery_id, gt.tag_id) for gt in existing_gallery_tags}

            desired_tag_pairs: set[tuple[int, int]] = set()
            for row, gallery in changed:
                for item in gallery.tags:
                    ns = str(item.get("namespace", "misc")).strip() or "misc"
                    name = str(item.get("name", "")).strip()
                    if name and (ns, name) in tag_map:
                        desired_tag_pairs.add((row.id, tag_map[(ns, name)].id))

            tags_to_add = desired_tag_pairs - existing_tag_pairs
            tags_to_remove = existing_tag_pairs - desired_tag_pairs

            if tags_to_remove:
                await self.session.execute(
                    delete(GalleryTag).where(
                        tuple_(GalleryTag.gallery_id, GalleryTag.tag_id).in_(list(tags_to_remove))
                    )
                )
            if tags_to_add:
                self.session.add_all(
                    GalleryTag(gallery_id=gid, tag_id=tid) for gid, tid in tags_to_add
                )
        else:
            await self.session.execute(
                delete(GalleryTag).where(GalleryTag.gallery_id.in_(changed_ids))
            )
        uploader_pairs = [
            (row.id, gallery.uploader)
            for row, gallery in changed
            if gallery.uploader
        ]
        if uploader_pairs:
            await _upsert_uploader_tag(self.session, uploader_pairs)
        await self.session.flush()

    async def fetch_existing_rows_raw(
        self, roots: Sequence[str | Path]
    ) -> list[dict[str, Any]]:
        """Fetch raw mappings for existing galleries under roots.

        Performs only the fast indexed SQL query and returns raw dicts,
        without holding the session for heavy exists subqueries, path
        resolution or object instantiation.
        """
        if not roots:
            return []
        normalized = [str(Path(root).resolve()) for root in roots]
        stmt = select(
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
            Gallery.local_rating,
        ).where(
            and_(
                Gallery.expunged.is_(False),
                or_(*(Gallery.storage_path.startswith(root) for root in normalized)),
            )
        )
        if hasattr(self.session, "execute"):
            result = await self.session.execute(stmt)
            if hasattr(result, "mappings"):
                return [dict(m) for m in result.mappings().all()]
            return [
                dict(row._mapping) if hasattr(row, "_mapping") else row
                for row in (result.all() if hasattr(result, "all") else [])
            ]
        else:
            result = await self.session.stream(stmt)
            raw = [row async for row in result]
            return [
                dict(row._mapping) if hasattr(row, "_mapping") else row
                for row in raw
            ]

    async def fetch_starred_and_custom_tag_metadata(
        self,
    ) -> tuple[set[int], set[int], set[int]]:
        """Fetch metadata sets for custom tags, favorites, and local lists.

        Returns:
            (custom_tag_gallery_ids, fav_gids, local_list_gallery_ids)
        """
        # 1. Custom tag gallery ids: tags in custom/local namespaces
        custom_tag_stmt = (
            select(GalleryTag.gallery_id)
            .join(Tag, GalleryTag.tag_id == Tag.id)
            .where(func.lower(Tag.namespace).in_(["local", "custom", "my", "user"]))
            .distinct()
        )
        if hasattr(self.session, "scalars"):
            custom_tag_ids = {int(gid) for gid in (await self.session.scalars(custom_tag_stmt)).all() if gid is not None}
        else:
            res = await self.session.execute(custom_tag_stmt)
            custom_tag_ids = {int(row[0]) for row in (res.all() if hasattr(res, "all") else res) if row[0] is not None}

        # 2. Favorite item gids
        fav_stmt = select(FavoriteItem.gid).where(FavoriteItem.gid.is_not(None)).distinct()
        if hasattr(self.session, "scalars"):
            fav_gids = {int(gid) for gid in (await self.session.scalars(fav_stmt)).all() if gid is not None}
        else:
            res = await self.session.execute(fav_stmt)
            fav_gids = {int(row[0]) for row in (res.all() if hasattr(res, "all") else res) if row[0] is not None}

        # 3. Local list item gallery ids
        local_list_stmt = select(LocalListItem.gallery_id).where(LocalListItem.gallery_id.is_not(None)).distinct()
        if hasattr(self.session, "scalars"):
            local_list_ids = {int(gid) for gid in (await self.session.scalars(local_list_stmt)).all() if gid is not None}
        else:
            res = await self.session.execute(local_list_stmt)
            local_list_ids = {int(row[0]) for row in (res.all() if hasattr(res, "all") else res) if row[0] is not None}

        return custom_tag_ids, fav_gids, local_list_ids

    @staticmethod
    def parse_existing_rows(
        raw_rows: Sequence[Mapping[str, Any] | Any],
        roots: Sequence[str | Path],
        *,
        custom_tag_ids: set[int] | None = None,
        fav_gids: set[int] | None = None,
        local_list_ids: set[int] | None = None,
    ) -> dict[str, ExistingGallery]:
        """Convert raw db rows to ExistingGallery dict in memory (outside session)."""
        if not roots or not raw_rows:
            return {}
        normalized = [str(Path(root).resolve()) for root in roots]
        out: dict[str, ExistingGallery] = {}
        for row in raw_rows:
            m = row._mapping if hasattr(row, "_mapping") else row
            path = m["storage_path"]
            if any(Path(path).resolve().is_relative_to(root) for root in normalized):
                gid = m.get("gid")
                gallery_id = m.get("id")
                local_rating = m.get("local_rating")

                gid_int = int(gid) if gid is not None else None
                id_int = int(gallery_id) if gallery_id is not None else None

                if "has_custom_tags" in m and m["has_custom_tags"] is not None:
                    has_custom_tags = bool(m["has_custom_tags"])
                elif custom_tag_ids is not None and id_int is not None:
                    has_custom_tags = id_int in custom_tag_ids
                else:
                    has_custom_tags = False

                if "is_favorited" in m and m["is_favorited"] is not None:
                    is_fav = bool(m["is_favorited"])
                elif fav_gids is not None and gid_int is not None:
                    is_fav = gid_int in fav_gids
                else:
                    is_fav = False

                if "in_local_list" in m and m["in_local_list"] is not None:
                    in_list = bool(m["in_local_list"])
                elif local_list_ids is not None and id_int is not None:
                    in_list = id_int in local_list_ids
                else:
                    in_list = False

                is_starred = bool(
                    (local_rating is not None and local_rating == 5)
                    or is_fav
                    or in_list
                )
                out[m["path_hash"]] = ExistingGallery(
                    path=path,
                    signature=m["storage_signature"],
                    gid=gid,
                    gallery_id=gallery_id,
                    storage_type=m["storage_type"],
                    title=m["title"],
                    title_jpn=m["title_jpn"],
                    file_count=m["file_count"],
                    file_size=m["file_size"],
                    posted_at=m["posted_at"],
                    local_rating=local_rating,
                    is_starred=is_starred,
                    rating=int(local_rating or 0),
                    has_custom_tags=has_custom_tags,
                )
        return out

    async def existing_rows(self, roots: Sequence[str | Path]) -> dict[str, ExistingGallery]:
        """Return path hash -> gallery row for non-expunged rows under ``roots``."""
        if not roots:
            return {}
        raw_rows = await self.fetch_existing_rows_raw(roots)
        custom_tag_ids, fav_gids, local_list_ids = await self.fetch_starred_and_custom_tag_metadata()
        return await run_in_threadpool(
            self.parse_existing_rows,
            raw_rows,
            roots,
            custom_tag_ids=custom_tag_ids,
            fav_gids=fav_gids,
            local_list_ids=local_list_ids,
        )

    async def sync_duplicates(self, groups) -> int:
        """Persist the duplicate groups a scan just produced.

        Open records are refreshed with the current copies; records the user
        dismissed or resolved are left alone (their decision wins).  Records
        whose gid is no longer duplicated (copy removed on disk, or resolved
        for real) are deleted.
        """
        from galleryvault.services.duplicate_resolver import ResolvedGroup

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

    async def fetch_expunge_candidates(self) -> list[dict[str, Any]]:
        """Short read: select active gallery paths and hashes without holding a transaction."""
        stmt = select(Gallery.id, Gallery.path_hash, Gallery.storage_path).where(
            Gallery.expunged.is_(False), Gallery.trashed.is_(False)
        )
        if hasattr(self.session, "execute"):
            result = await self.session.execute(stmt)
            if hasattr(result, "mappings"):
                return [dict(m) for m in result.mappings().all()]
            return [
                dict(row._mapping) if hasattr(row, "_mapping") else row
                for row in (result.all() if hasattr(result, "all") else [])
            ]
        else:
            result = await self.session.stream(stmt)
            raw = [row async for row in result]
            return [
                dict(row._mapping) if hasattr(row, "_mapping") else row
                for row in raw
            ]

    @staticmethod
    def find_missing_ids(
        candidates: Sequence[Mapping[str, Any] | Any],
        roots: Sequence[str | Path],
        seen: set[str],
    ) -> list[int]:
        """In-memory comparison: find IDs of galleries missing from disk.

        Rows ingested through a symlink that escapes every configured root keep
        the ``path_hash`` of the resolved target, so no scan can ever list them
        as seen and they used to stay forever.  Such a row counts as missing
        when its literal (unresolved) path is still inside a root.  Rows whose
        root is no longer configured keep the old behaviour and are ignored.
        """
        if not roots or not candidates:
            return []
        resolved_roots = [Path(root).resolve() for root in roots]
        # Keep the un-followed spelling of each root too, so a root that is
        # itself a symlink still matches legacy rows stored with that spelling.
        literal_roots = [*resolved_roots]
        literal_roots.extend(Path(os.path.abspath(str(root))) for root in roots)
        missing_ids: list[int] = []
        for row in candidates:
            m = row._mapping if hasattr(row, "_mapping") else row
            storage_path = m["storage_path"]
            if not storage_path:
                continue
            path = Path(storage_path).resolve()
            in_roots = any(path.is_relative_to(root) for root in resolved_roots)
            if not in_roots:
                literal = Path(os.path.abspath(str(storage_path)))
                in_roots = any(literal.is_relative_to(root) for root in literal_roots)
            if in_roots and m["path_hash"] not in seen:
                missing_ids.append(m["id"])
        return missing_ids

    async def mark_expunged(self, ids: list[int]) -> int:
        """Short write: mark the given IDs as expunged in batches."""
        if not ids:
            return 0
        for start in range(0, len(ids), 5000):
            await self._mark_expunged(ids[start : start + 5000])
        await self.session.flush()
        return len(ids)

    async def expunge_missing(self, roots: Sequence[str | Path], seen: set[str]) -> int:
        candidates = await self.fetch_expunge_candidates()
        missing_ids = await run_in_threadpool(self.find_missing_ids, candidates, roots, seen)
        if missing_ids:
            await self.mark_expunged(missing_ids)
        return len(missing_ids)

    async def _mark_expunged(self, ids: list[int]) -> None:
        await self.session.execute(
            update(Gallery)
            .where(Gallery.id.in_(ids))
            .values(expunged=True, updated_at=datetime.now(UTC))
        )

    async def restore_galleries(self, ids: list[int]) -> int:
        if not ids:
            return 0
        result = await self.session.execute(
            update(Gallery)
            .where(Gallery.id.in_(ids), Gallery.trashed.is_(True))
            .values(trashed=False, trashed_at=None, updated_at=datetime.now(UTC))
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

    async def sync_categories_from_metadata(self) -> int:
        """Bulk update galleries with 'misc'/'other' category from gallery_metadata."""
        statement = (
            update(Gallery)
            .where(
                Gallery.gid == GalleryMetadata.gid,
                Gallery.category.in_(["misc", "other"]),
                GalleryMetadata.category.is_not(None),
                GalleryMetadata.category.not_in(["misc", "other"]),
            )
            .values(
                category=GalleryMetadata.category,
                category_refreshed_at=func.now(),
            )
        )
        result = await self.session.execute(statement)
        await self.session.flush()
        return int(result.rowcount or 0)

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
            posted_at = None
            if posted:
                try:
                    posted_at = datetime.fromtimestamp(int(posted), tz=UTC)
                except (ValueError, OSError, OverflowError, TypeError):
                    posted_at = None
            elif isinstance(e.get("posted_at"), datetime):
                posted_at = e["posted_at"]

            raw_tags = e.get("tags") or []
            tags = []
            for item in raw_tags:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    tags.append([str(item[0] or "misc"), str(item[1])])
                elif isinstance(item, dict):
                    tags.append([str(item.get("namespace") or "misc"), str(item.get("name") or "")])
                elif isinstance(item, str) and item:
                    parts = item.split(":", 1)
                    tags.append(parts if len(parts) == 2 else ["misc", item])

            parent_gid = None
            if e.get("parent_gid") is not None:
                try:
                    parent_gid = int(e["parent_gid"])
                except (ValueError, TypeError):
                    parent_gid = None
            elif e.get("parent") is not None:
                try:
                    parent_gid = int(e["parent"])
                except (ValueError, TypeError):
                    parent_gid = None

            thumb = e.get("thumb") or None
            if thumb is not None:
                thumb = str(thumb).strip() or None

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
                    "parent_gid": parent_gid,
                    "thumb": thumb,
                    "updated_at": now,
                }
            )
        batch_size = 500
        written = 0
        for start in range(0, len(rows), batch_size):
            statement = pg_insert(GalleryMetadata).values(rows[start : start + batch_size])
            excluded = statement.excluded
            # gdata omits fields for some galleries (title / posted / filesize …),
            # and the fetch layer turns those into None. Never let a partial
            # response overwrite metadata already cached from a complete one:
            # keep the stored value unless it is still empty. ``expunged`` is
            # sticky for the same reason (a True flag is a fact, not a default).
            updates = {
                "token": func.coalesce(excluded.token, GalleryMetadata.token),
                "title": func.coalesce(excluded.title, GalleryMetadata.title),
                "title_jpn": func.coalesce(excluded.title_jpn, GalleryMetadata.title_jpn),
                "category": func.coalesce(excluded.category, GalleryMetadata.category),
                "uploader": func.coalesce(excluded.uploader, GalleryMetadata.uploader),
                "file_count": func.coalesce(excluded.file_count, GalleryMetadata.file_count),
                "file_size": func.coalesce(excluded.file_size, GalleryMetadata.file_size),
                "rating": func.coalesce(excluded.rating, GalleryMetadata.rating),
                "posted_at": func.coalesce(excluded.posted_at, GalleryMetadata.posted_at),
                "expunged": or_(GalleryMetadata.expunged, excluded.expunged),
                "tags": case(
                    (
                        or_(
                            excluded.tags.is_(None),
                            func.jsonb_array_length(excluded.tags) == 0,
                        ),
                        GalleryMetadata.tags,
                    ),
                    else_=excluded.tags,
                ),
                "parent_gid": func.coalesce(excluded.parent_gid, GalleryMetadata.parent_gid),
                "thumb": func.coalesce(excluded.thumb, GalleryMetadata.thumb),
                "updated_at": excluded.updated_at,
            }
            statement = statement.on_conflict_do_update(
                index_elements=["gid"],
                set_=updates,
                # Only advance updated_at when the content actually changed, so a
                # later metadata-apply pass can tell "fresh" from "same as last
                # time" without rewriting local galleries every check. Compare the
                # coalesced values: an all-None payload resolves to the stored
                # values and must not count as a change.
                where=or_(
                    GalleryMetadata.token.is_distinct_from(updates["token"]),
                    GalleryMetadata.tags.is_distinct_from(updates["tags"]),
                    GalleryMetadata.category.is_distinct_from(updates["category"]),
                    GalleryMetadata.title.is_distinct_from(updates["title"]),
                    GalleryMetadata.title_jpn.is_distinct_from(updates["title_jpn"]),
                    GalleryMetadata.uploader.is_distinct_from(updates["uploader"]),
                    GalleryMetadata.posted_at.is_distinct_from(updates["posted_at"]),
                    GalleryMetadata.file_size.is_distinct_from(updates["file_size"]),
                    GalleryMetadata.file_count.is_distinct_from(updates["file_count"]),
                    GalleryMetadata.rating.is_distinct_from(updates["rating"]),
                    GalleryMetadata.expunged.is_distinct_from(updates["expunged"]),
                    GalleryMetadata.parent_gid.is_distinct_from(updates["parent_gid"]),
                    GalleryMetadata.thumb.is_distinct_from(updates["thumb"]),
                ),
            )
            result = await self.session.execute(statement)
            written += result.rowcount or 0
        return written

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
                null(),
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

    async def null_image_quality_gids(self, gids: list[int]) -> set[int]:
        """Local gids whose ``image_quality`` is still NULL."""
        if not gids:
            return set()
        rows = (
            await self.session.scalars(
                select(Gallery.gid).where(
                    Gallery.gid.in_(list(dict.fromkeys(gids))),
                    Gallery.image_quality.is_(None),
                )
            )
        ).all()
        return {int(gid) for gid in rows}

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

    async def apply_cached_metadata(
        self,
        galleries: Sequence[Gallery] | None = None,
        *,
        favcat: int | None = None,
        limit: int = 200,
    ) -> int:
        """Apply fresh cached metadata to local galleries.

        Can target an explicit sequence of local ``Gallery`` objects, a
        favorite folder (``favcat``), or all pending on-disk galleries.
        For every gallery whose metadata cache is newer than its last tag
        sync (or explicitly provided), updates tags (replacing ``gallery_tags``),
        category, title, title_jpn, uploader, posted_at, file_count, rating,
        expunged (if explicitly expunged in cache), parent relation, and stamps
        ``tags_synced_at``. Returns the number of galleries updated.
        """
        if galleries is not None:
            gids = [g.gid for g in galleries if g.gid is not None]
            if not gids:
                return 0
            meta_rows = await self.session.scalars(
                select(GalleryMetadata).where(GalleryMetadata.gid.in_(gids))
            )
            meta_by_gid = {m.gid: m for m in meta_rows}
            pairs = [(g, meta_by_gid[g.gid]) for g in galleries if g.gid in meta_by_gid]
        elif favcat is not None:
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
        else:
            rows = await self.session.execute(
                select(Gallery, GalleryMetadata)
                .join(GalleryMetadata, GalleryMetadata.gid == Gallery.gid)
                .where(
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
        tag_gallery_ids: list[int] = []
        for gallery, meta in pairs:
            gallery.category = meta.category or gallery.category
            gallery.title = meta.title or gallery.title
            gallery.title_jpn = meta.title_jpn or gallery.title_jpn
            gallery.uploader = meta.uploader or gallery.uploader
            gallery.file_count = meta.file_count or gallery.file_count
            if getattr(meta, "rating", None) is not None:
                gallery.rating = meta.rating
            gallery.posted_at = meta.posted_at or gallery.posted_at
            if getattr(meta, "expunged", False):
                gallery.expunged = True
            parent_gid = getattr(meta, "parent_gid", None)
            if parent_gid is not None and hasattr(gallery, "source_meta"):
                source_meta = dict(gallery.source_meta or {})
                source_meta["parent_gid"] = parent_gid
                gallery.source_meta = source_meta
            gallery.tags_synced_at = now
            meta_tags = meta.tags or []
            if meta_tags:
                tag_gallery_ids.append(gallery.id)
                for tag in meta_tags:
                    if isinstance(tag, dict):
                        namespace = str(tag.get("namespace") or "misc").strip() or "misc"
                        name = str(tag.get("name") or "").strip()
                    elif isinstance(tag, (list, tuple)) and len(tag) == 2:
                        namespace = str(tag[0] or "misc").strip() or "misc"
                        name = str(tag[1] or "").strip()
                    elif isinstance(tag, str):
                        parts = tag.split(":", 1)
                        namespace = parts[0].strip() or "misc" if len(parts) == 2 else "misc"
                        name = parts[1].strip() if len(parts) == 2 else parts[0].strip()
                    else:
                        continue
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
            gallery_tag_rows = []
            for gallery, meta in pairs:
                meta_tags = meta.tags or []
                for tag in meta_tags:
                    if isinstance(tag, dict):
                        namespace = str(tag.get("namespace") or "misc").strip() or "misc"
                        name = str(tag.get("name") or "").strip()
                    elif isinstance(tag, (list, tuple)) and len(tag) == 2:
                        namespace = str(tag[0] or "misc").strip() or "misc"
                        name = str(tag[1] or "").strip()
                    elif isinstance(tag, str):
                        parts = tag.split(":", 1)
                        namespace = parts[0].strip() or "misc" if len(parts) == 2 else "misc"
                        name = parts[1].strip() if len(parts) == 2 else parts[0].strip()
                    else:
                        continue
                    key = (namespace, name)
                    if key in tag_map:
                        gallery_tag_rows.append(
                            {
                                "gallery_id": gallery.id,
                                "tag_id": tag_map[key].id,
                            }
                        )
            if gallery_tag_rows:
                await self.session.execute(
                    pg_insert(GalleryTag)
                    .values(gallery_tag_rows)
                    .on_conflict_do_nothing(index_elements=["gallery_id", "tag_id"])
                )

        uploader_pairs = [
            (gallery.id, gallery.uploader)
            for gallery, _ in pairs
            if gallery.uploader
        ]
        if uploader_pairs:
            await _upsert_uploader_tag(self.session, uploader_pairs)

        return len(pairs)

    async def apply_metadata_to_galleries(self, favcat: int, limit: int = 200) -> int:
        """Backward-compatible alias for apply_cached_metadata(favcat=favcat, limit=limit)."""
        return await self.apply_cached_metadata(favcat=favcat, limit=limit)

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
        await self.session.execute(
            delete(GalleryTag).where(
                GalleryTag.gallery_id == gallery.id,
                ~GalleryTag.tag_id.in_(select(Tag.id).where(Tag.namespace == "local")),
            )
        )
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

    async def set_local_tags(self, gallery_id: int, names: Sequence[str]) -> int:
        """Replace only ``local:`` tags for a gallery; EH tags are untouched."""
        await self.session.execute(
            delete(GalleryTag).where(
                GalleryTag.gallery_id == gallery_id,
                GalleryTag.tag_id.in_(select(Tag.id).where(Tag.namespace == "local")),
            )
        )
        await self.session.flush()
        unique: list[str] = []
        seen: set[str] = set()
        for raw in names:
            name = str(raw or "").strip()
            if ":" in name:
                name = name.split(":", 1)[-1].strip()
            if not name or name in seen:
                continue
            seen.add(name)
            unique.append(name)
        if not unique:
            return 0
        await self.session.execute(
            pg_insert(Tag)
            .values([{"namespace": "local", "name": name} for name in unique])
            .on_conflict_do_nothing(index_elements=["namespace", "name"])
        )
        await self.session.flush()
        existing = (
            await self.session.scalars(
                select(Tag).where(Tag.namespace == "local", Tag.name.in_(unique))
            )
        ).all()
        if existing:
            await self.session.execute(
                pg_insert(GalleryTag)
                .values(
                    [{"gallery_id": gallery_id, "tag_id": tag.id} for tag in existing]
                )
                .on_conflict_do_nothing(index_elements=["gallery_id", "tag_id"])
            )
            await self.session.flush()
        return len(existing)

    async def update_titles(
        self,
        gallery_id: int,
        title: str | None,
        title_jpn: str | None,
    ) -> bool:
        """Update gallery title and title_jpn when clean metadata is available."""
        gallery = await self.session.get(Gallery, gallery_id)
        if gallery is None:
            return False
        changed = False
        if title is not None:
            clean_title = str(title).strip()
            if clean_title and gallery.title != clean_title:
                gallery.title = clean_title
                changed = True
        if title_jpn is not None:
            clean_jpn = str(title_jpn).strip()
            if clean_jpn and not clean_jpn.isdigit() and gallery.title_jpn != clean_jpn:
                gallery.title_jpn = clean_jpn
                changed = True
        if changed:
            await self.session.flush()
        return changed

    async def trash_galleries(self, ids: Sequence[int]) -> int:
        """Mark galleries as trashed (soft delete)."""
        valid_ids = [i for i in ids if i is not None]
        if not valid_ids:
            return 0
        now = datetime.now(UTC)
        count = 0
        for chunk in _chunked(valid_ids):
            result = await self.session.execute(
                update(Gallery)
                .where(Gallery.id.in_(chunk), Gallery.trashed.is_(False))
                .values(trashed=True, trashed_at=now, updated_at=now)
            )
            count += int(result.rowcount or 0)
        await self.session.flush()
        return count

    async def set_local_rating(self, gallery_id: int, rating: int | None) -> bool:
        """Update local rating for a gallery."""
        gallery = await self.get_by_id(gallery_id)
        if gallery is None:
            return False
        gallery.local_rating = rating
        gallery.updated_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def update_gallery_fields(
        self, gallery_id: int, **kwargs: Any
    ) -> Gallery | None:
        """Update arbitrary gallery attributes."""
        gallery = await self.get_by_id(gallery_id)
        if gallery is None:
            return None
        for key, value in kwargs.items():
            if hasattr(gallery, key):
                setattr(gallery, key, value)
        gallery.updated_at = datetime.now(UTC)
        await self.session.flush()
        return gallery
