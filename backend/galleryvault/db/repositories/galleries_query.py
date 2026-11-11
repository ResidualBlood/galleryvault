"""Read-only query methods of ``GalleryRepository`` (mixins split).

Pure move out of ``db.repositories.galleries``: the 41 read-side methods now
live on ``GalleryQueryMixin`` so the repository can be assembled from focused
mixins while keeping a single concrete class (class-attribute monkeypatches
such as ``GalleryRepository.list_page`` keep working).

The mixin only relies on ``self.session`` (an ``AsyncSession`` or a test
double); it never touches ``model_cls`` or other repository state, so it can be
mixed into any repository exposing a session.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    DuplicateRecord,
    FavoriteItem,
    Gallery,
    GalleryMetadata,
    GalleryPage,
    GalleryTag,
    GalleryUpdate,
    LocalListItem,
    ReadingHistory,
    ReadingProgress,
    Tag,
)
from ..tag_filters import build_tag_predicates
from .base import _chunked, count_select, escape_like_wildcards
from .galleries_common import _title_sort_column


class GalleryQueryMixin:
    """Read-only gallery queries (requires ``self.session``)."""

    session: AsyncSession

    async def get_by_id(self, gallery_id: Any) -> Gallery | None:
        """Fetch gallery by primary key with mock-session fallback."""
        get_fn = getattr(self.session, "get", None)
        if callable(get_fn):
            return await get_fn(Gallery, gallery_id)
        return await self.session.scalar(select(Gallery).where(Gallery.id == gallery_id))

    async def list_page(
        self,
        page: int,
        page_size: int,
        q: str | None = None,
        tags: Sequence[tuple[str | None, str]] = (),
        exclude_tags: Sequence[tuple[str | None, str]] = (),
        tag_mode: str = "or",
        tag_match: str = "exact",
        tag_id_map: Mapping[tuple[str | None, str], int] | None = None,
        category: str | None = None,
        exclude_favorited: bool = False,
        order_by: str = "id_desc",
        read_status: str | None = None,
        min_rating: float | None = None,
        page_min: int | None = None,
        page_max: int | None = None,
        size_min: int | None = None,
        size_max: int | None = None,
        posted_from: datetime | None = None,
        posted_to: datetime | None = None,
        uploader: str | None = None,
        image_quality: str | None = None,
        min_local_rating: int | None = None,
        list_id: int | None = None,
        title_display: str | None = None,
        favorite: bool | None = None,
        read: bool | None = None,
        expunged: bool | None = None,
        media_type: str | None = None,
        storage_type: str | None = None,
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
        size_col = func.coalesce(Gallery.storage_size, Gallery.file_size)
        if size_min is not None:
            query = query.where(size_col >= size_min)
        if size_max is not None:
            query = query.where(size_col <= size_max)
        if posted_from is not None:
            query = query.where(Gallery.posted_at >= posted_from)
        if posted_to is not None:
            query = query.where(Gallery.posted_at <= posted_to)
        if uploader and uploader.strip():
            pattern = f"%{escape_like_wildcards(uploader.strip())}%"
            query = query.where(Gallery.uploader.ilike(pattern))
        if image_quality:
            query = query.where(Gallery.image_quality == image_quality)
        if min_local_rating is not None:
            query = query.where(Gallery.local_rating >= min_local_rating)
        if list_id is not None:
            in_list = (
                select(1)
                .select_from(LocalListItem)
                .where(
                    LocalListItem.list_id == list_id,
                    LocalListItem.gallery_id == Gallery.id,
                )
            )
            query = query.where(in_list.exists())
        if exclude_favorited or favorite is not None:
            # A local gallery is favorited when its gid is in a favorite folder
            # or when a tracked update points at a favorited new_gid.
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
            is_favorited = Gallery.gid.is_not(None) & (
                fav_exists.exists() | updated_fav_exists.exists()
            )
            if exclude_favorited:
                query = query.where(~is_favorited)
            if favorite is True:
                query = query.where(is_favorited)
            elif favorite is False:
                query = query.where(~is_favorited)
        completed_exists = (
            select(1)
            .select_from(ReadingProgress)
            .where(
                ReadingProgress.gallery_id == Gallery.id,
                ReadingProgress.total_pages.is_not(None),
                ReadingProgress.current_page >= ReadingProgress.total_pages - 1,
                or_(
                    ReadingProgress.current_page > 0,
                    ReadingProgress.total_pages <= 1,
                ),
            )
        )
        if read_status == "unread":
            started_exists = select(1).select_from(ReadingProgress).where(
                ReadingProgress.gallery_id == Gallery.id,
                ReadingProgress.current_page > 0,
            )
            query = query.where(~started_exists.exists(), ~completed_exists.exists())
        elif read_status == "reading":
            prog_exists = select(1).select_from(ReadingProgress).where(
                ReadingProgress.gallery_id == Gallery.id,
                ReadingProgress.current_page > 0,
                (
                    ReadingProgress.total_pages.is_(None)
                    | (ReadingProgress.current_page < ReadingProgress.total_pages - 1)
                ),
            )
            query = query.where(prog_exists.exists(), ~completed_exists.exists())
        elif read_status in {"completed", "read"}:
            query = query.where(completed_exists.exists())
        if read is True:
            query = query.where(completed_exists.exists())
        elif read is False:
            query = query.where(~completed_exists.exists())
        tag_predicates = build_tag_predicates(
            Gallery.id,
            tags=tags,
            exclude_tags=exclude_tags,
            tag_mode=tag_mode,
            tag_match=tag_match,
            tag_id_map=tag_id_map,
        )
        if tag_predicates:
            query = query.where(*tag_predicates)
        if expunged is True:
            query = query.where(Gallery.expunged.is_(True))
        else:
            query = query.where(Gallery.expunged.is_(False))
        if storage_type:
            query = query.where(Gallery.storage_type == storage_type)
        if media_type:
            has_media = select(1).select_from(GalleryPage).where(
                GalleryPage.gallery_id == Gallery.id,
                GalleryPage.media_type == media_type,
            )
            query = query.where(has_media.exists())
        query = query.where(Gallery.trashed.is_(False))
        total = await count_select(self.session, query)
        title_col = _title_sort_column(title_display)
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

    async def resolve_exact_tags(
        self,
        tags: Sequence[tuple[str | None, str]],
    ) -> dict[tuple[str | None, str], int]:
        candidates: list[tuple[str, str]] = []
        for ns, name in tags:
            if ns is not None and name and name.strip():
                candidates.append((ns.strip(), name.strip()))
        if not candidates:
            return {}

        unique_candidates: list[tuple[str, str]] = []
        seen = set()
        for item in candidates:
            if item not in seen:
                seen.add(item)
                unique_candidates.append(item)

        resolved: dict[tuple[str | None, str], int] = {}
        # 1. Exact match on (namespace, name) using tags_namespace_name_key
        stmt = select(Tag.id, Tag.namespace, Tag.name).where(
            tuple_(Tag.namespace, Tag.name).in_(unique_candidates)
        )
        rows = (await self.session.execute(stmt)).all()
        for tag_id, ns, name in rows:
            resolved[(ns, name)] = tag_id

        # 2. For unresolved candidates, fallback to case-insensitive match
        unresolved = [pair for pair in unique_candidates if pair not in resolved]
        for ns, name in unresolved:
            stmt_lower = select(Tag.id).where(
                func.lower(Tag.namespace) == ns.lower(),
                func.lower(Tag.name) == name.lower(),
            )
            matched_ids = (await self.session.scalars(stmt_lower)).all()
            # Clause 3: 查不到唯一 tag 则回落 ILIKE
            if len(matched_ids) == 1:
                resolved[(ns, name)] = matched_ids[0]

        return resolved

    async def search_tags(
        self, q: str | None, page: int, page_size: int, namespace: str | None = None
    ) -> tuple[int, list[tuple[str, str, int]]]:
        pattern = f"%{escape_like_wildcards(q.strip())}%" if q and q.strip() else None
        match = select(Tag.id).select_from(Tag)
        if namespace:
            match = match.where(Tag.namespace == namespace)
        if pattern:
            match = match.where(Tag.name.ilike(pattern) | Tag.namespace.ilike(pattern))
        total = await count_select(self.session, match)
        # Limit the tag rows first, then compute usage counts only for the
        # visible page — counting usage for every matching tag then slicing was
        # a full-table aggregation on large libraries.
        page_ids_query = (
            match.order_by(Tag.namespace, Tag.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        page_ids_list = list((await self.session.scalars(page_ids_query)).all())
        if not page_ids_list:
            return total, []
        rows = (
            await self.session.execute(
                select(Tag.namespace, Tag.name, func.count(Gallery.id))
                .select_from(Tag)
                .outerjoin(GalleryTag, GalleryTag.tag_id == Tag.id)
                .outerjoin(
                    Gallery,
                    and_(Gallery.id == GalleryTag.gallery_id, Gallery.expunged.is_(False)),
                )
                .where(Tag.id.in_(page_ids_list))
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

    async def category_counts(self) -> list[tuple[str, int]]:
        """Gallery counts per category for the category pills.

        Only usable rows are counted (not expunged, not trashed) and rows with
        no category are skipped instead of being bucketed under ``None``.
        """
        rows = await self.session.execute(
            select(Gallery.category, func.count(Gallery.id))
            .where(
                Gallery.expunged.is_(False),
                Gallery.trashed.is_(False),
                Gallery.category.is_not(None),
            )
            .group_by(Gallery.category)
            .order_by(func.count(Gallery.id).desc(), Gallery.category)
        )
        return [(category, int(count)) for category, count in rows]

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
        tag_rows = (
            await self.session.execute(
                select(Tag.id, Tag.namespace, Tag.name).where(
                    tuple_(Tag.namespace, Tag.name).in_(list(pairs))
                )
            )
        ).all()
        if not tag_rows:
            return []
        tag_ids = [row[0] for row in tag_rows]
        rows = (
            await self.session.execute(
                select(Tag.namespace, Tag.name, func.count(Gallery.id))
                .select_from(Tag)
                .join(GalleryTag, GalleryTag.tag_id == Tag.id)
                .join(
                    Gallery, and_(Gallery.id == GalleryTag.gallery_id, Gallery.expunged.is_(False))
                )
                .where(Tag.id.in_(tag_ids))
                .group_by(Tag.id)
            )
        ).all()
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
        total = await count_select(self.session, query)
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
        total = await count_select(self.session, query)
        rows = (
            await self.session.scalars(
                query.order_by(Gallery.updated_at.desc(), Gallery.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return total, list(rows)

    async def list_integrity_issues(
        self, page: int, page_size: int, extra_ids: Sequence[int] | None = None
    ) -> tuple[int, list[Gallery]]:
        # Page count vs actual gallery_pages rows, excluding trashed/expunged
        page_count_sub = (
            select(GalleryPage.gallery_id, func.count(GalleryPage.id).label("cnt"))
            .group_by(GalleryPage.gallery_id)
            .subquery()
        )
        count_mismatch_query = (
            select(Gallery)
            .outerjoin(page_count_sub, page_count_sub.c.gallery_id == Gallery.id)
            .where(Gallery.trashed.is_(False), Gallery.expunged.is_(False))
            .where(Gallery.page_count.is_not(None))
            .where(Gallery.page_count != func.coalesce(page_count_sub.c.cnt, 0))
        )
        mismatched_rows = list((await self.session.scalars(count_mismatch_query)).all())

        combined: dict[int, Gallery] = {g.id: g for g in mismatched_rows}
        if extra_ids:
            extra_query = select(Gallery).where(
                Gallery.id.in_(list(extra_ids)),
                Gallery.trashed.is_(False),
                Gallery.expunged.is_(False),
            )
            for g in (await self.session.scalars(extra_query)).all():
                combined[g.id] = g

        all_issues = sorted(combined.values(), key=lambda x: x.id, reverse=True)
        total = len(all_issues)
        start = (page - 1) * page_size
        return total, all_issues[start : start + page_size]

    async def list_magic_scan_targets(
        self, after_id: int = 0, limit: int = 200
    ) -> list[Gallery]:
        page_count_sub = (
            select(GalleryPage.gallery_id, func.count(GalleryPage.id).label("cnt"))
            .group_by(GalleryPage.gallery_id)
            .subquery()
        )
        complete_query = (
            select(Gallery)
            .outerjoin(page_count_sub, page_count_sub.c.gallery_id == Gallery.id)
            .where(Gallery.trashed.is_(False), Gallery.expunged.is_(False))
            .where(Gallery.page_count.is_not(None))
            .where(Gallery.page_count == func.coalesce(page_count_sub.c.cnt, 0))
            .where(Gallery.id > after_id)
            .order_by(Gallery.id)
            .limit(limit)
        )
        return list((await self.session.scalars(complete_query)).all())

    async def progress(self, gallery_id: int) -> ReadingProgress | None:
        return await self.session.get(ReadingProgress, gallery_id)

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
                Gallery.category.in_(["other", "misc"]),
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
                Gallery.category.in_(["other", "misc"]),
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

    async def get_by_gid(self, gid: int) -> Gallery | None:
        """Fetch a live gallery by ExHentai ``gid``.

        ``gid`` is not unique in the schema (rescans may leave duplicate rows)
        and trashed/expunged rows must not be served, so take the newest live
        row explicitly instead of ``scalar_one_or_none``.
        """
        return await self.session.scalar(
            select(Gallery)
            .where(
                Gallery.gid == gid,
                Gallery.expunged.is_(False),
                Gallery.trashed.is_(False),
            )
            .order_by(Gallery.id.desc())
            .limit(1)
        )

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
                    "gid": int(row.gid),
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
                    "parent_gid": row.parent_gid,
                    "newer_gid": row.newer_gid,
                    "is_replaced": row.is_replaced,
                    "thumb": row.thumb,
                    "updated_at": row.updated_at,
                }
        return result

    async def metadata_for_gid(self, gid: int) -> dict | None:
        return (await self.metadata_map([gid])).get(gid)

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

    async def largest_by_storage(self, limit: int = 10) -> list[Gallery]:
        size_col = func.coalesce(Gallery.storage_size, Gallery.file_size)
        rows = (
            await self.session.scalars(
                select(Gallery)
                .where(
                    Gallery.expunged.is_(False),
                    Gallery.trashed.is_(False),
                    size_col.is_not(None),
                    size_col > 0,
                )
                .order_by(size_col.desc(), Gallery.id.desc())
                .limit(limit)
            )
        ).all()
        return list(rows)

    async def library_storage_sum(self) -> int:
        size_col = func.coalesce(Gallery.storage_size, Gallery.file_size)
        value = await self.session.scalar(
            select(func.coalesce(func.sum(size_col), 0)).where(
                Gallery.expunged.is_(False), Gallery.trashed.is_(False)
            )
        )
        return int(value or 0)

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

    async def get_gallery_with_pages(
        self, gallery_id: int
    ) -> tuple[Gallery, list[GalleryPage]] | None:
        """Fetch gallery by id and its pages ordered by page_index."""
        gallery = await self.get_by_id(gallery_id)
        if gallery is None:
            return None
        pages = list(
            (
                await self.session.scalars(
                    select(GalleryPage)
                    .where(GalleryPage.gallery_id == gallery_id)
                    .order_by(GalleryPage.page_index)
                )
            ).all()
        )
        return gallery, pages

    async def get_pages(self, gallery_id: int) -> list[GalleryPage]:
        """Fetch pages for gallery ordered by page_index."""
        return list(
            (
                await self.session.scalars(
                    select(GalleryPage)
                    .where(GalleryPage.gallery_id == gallery_id)
                    .order_by(GalleryPage.page_index)
                )
            ).all()
        )

    async def tags_for_gallery(self, gallery_id: int) -> list[tuple[str, str]]:
        """Fetch all tags for a single gallery as (namespace, name) tuples."""
        rows = await self.session.execute(
            select(Tag.namespace, Tag.name)
            .join(GalleryTag, GalleryTag.tag_id == Tag.id)
            .where(GalleryTag.gallery_id == gallery_id)
            .order_by(Tag.namespace, Tag.name)
        )
        return [(ns, name) for ns, name in rows]

    async def find_by_gids(self, gids: Sequence[int]) -> list[Gallery]:
        """Fetch galleries matching provided gids."""
        return await self.get_by_ids(gids, id_attr="gid")

    async def find_by_ids(self, ids: Sequence[int]) -> list[Gallery]:
        """Fetch galleries matching provided primary key ids."""
        return await self.get_by_ids(ids, id_attr="id")

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
