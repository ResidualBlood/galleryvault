"""Metadata and tag write methods of ``GalleryRepository`` (mixins split).

Pure move out of ``db.repositories.galleries``: the 18 metadata / tag mutation
methods now live on ``GalleryMetadataMixin`` so the repository can be assembled
from focused mixins while keeping a single concrete class (class-attribute
monkeypatches such as ``GalleryRepository.upsert_metadata`` keep working).

The mixin only relies on ``self.session`` (an ``AsyncSession`` or a test
double) plus ``self.get_by_id`` from the query mixin.  Unlike the methods that
stayed in ``galleries``, it resolves the shared ``_upsert_uploader_tag`` helper
through :mod:`galleries_common` directly, so patching
``galleries._upsert_uploader_tag`` no longer affects ``apply_cached_metadata``
(the ``services.tag_sync`` call-time import path is unaffected).
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, delete, func, null, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...scanners.base import normalize_category
from ..models import (
    FavoriteItem,
    Gallery,
    GalleryMetadata,
    GalleryTag,
    LocalListItem,
    Tag,
)
from . import galleries_common


class GalleryMetadataMixin:
    """Cached metadata, tag writes and local field edits (needs ``self.session``)."""

    session: AsyncSession

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
            await galleries_common._upsert_uploader_tag(self.session, uploader_pairs)

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
