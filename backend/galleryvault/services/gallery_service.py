from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ..app.dependencies import BatchOperationResult, PageParams, PageResponse
from ..app.exceptions import NotFoundError, ValidationError
from ..db.models import Gallery, GalleryPage
from .base_service import BaseService


class GalleryService(BaseService):
    """Service encapsulating gallery querying, modification, tagging,

    reading progress, and deletion workflows.
    """

    async def list_galleries(
        self,
        page_params: PageParams | None = None,
        page: int | None = None,
        page_size: int | None = None,
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
        size_min: int | None = None,
        size_max: int | None = None,
        posted_from: datetime | None = None,
        posted_to: datetime | None = None,
        uploader: str | None = None,
        image_quality: str | None = None,
        min_local_rating: int | None = None,
        list_id: int | None = None,
        title_display: str | None = None,
    ) -> PageResponse[Any]:
        """Query galleries with filtering, search, and pagination."""
        actual_page = page or (page_params.page if page_params else 1)
        actual_page_size = page_size or (page_params.page_size if page_params else 50)

        # Resolve exact tags map if tags are provided
        tag_id_map = None
        if tags or exclude_tags:
            all_tags = list(tags) + list(exclude_tags)
            tag_id_map = await self.uow.galleries.resolve_exact_tags(all_tags)

        total, items = await self.uow.galleries.list_page(
            page=actual_page,
            page_size=actual_page_size,
            q=q,
            tags=tags,
            exclude_tags=exclude_tags,
            tag_mode=tag_mode,
            tag_match=tag_match,
            tag_id_map=tag_id_map,
            category=category,
            exclude_favorited=exclude_favorited,
            order_by=order_by,
            read_status=read_status,
            min_rating=min_rating,
            page_min=page_min,
            page_max=page_max,
            size_min=size_min,
            size_max=size_max,
            posted_from=posted_from,
            posted_to=posted_to,
            uploader=uploader,
            image_quality=image_quality,
            min_local_rating=min_local_rating,
            list_id=list_id,
            title_display=title_display,
        )

        return PageResponse.create(
            items=items,
            total=total,
            params=PageParams(page=actual_page, page_size=actual_page_size),
        )

    async def get_gallery(self, identifier: int) -> Gallery:
        """Fetch gallery by id or gid; raises NotFoundError if missing."""
        gallery = await self.uow.galleries.get_by_identifier(identifier)
        if gallery is None:
            raise NotFoundError(f"Gallery {identifier} not found")
        return gallery

    async def get_pages(self, gallery_id: int) -> list[GalleryPage]:
        """Fetch all pages belonging to a gallery."""
        gallery = await self.uow.galleries.get_by_id(gallery_id)
        if gallery is None:
            raise NotFoundError(f"Gallery {gallery_id} not found")
        return await self.uow.galleries.get_pages(gallery_id)

    async def set_local_rating(self, gallery_id: int, rating: int | None) -> Gallery:
        """Set or clear local rating for a gallery."""
        if rating is not None and not (0 <= rating <= 5):
            raise ValidationError("Rating must be between 0 and 5")
        async with self.transaction():
            updated = await self.uow.galleries.set_local_rating(gallery_id, rating)
            if not updated:
                raise NotFoundError(f"Gallery {gallery_id} not found")
            gallery = await self.uow.galleries.get_by_id(gallery_id)
            if gallery is None:
                raise NotFoundError(f"Gallery {gallery_id} not found")
            return gallery

    async def set_local_tags(
        self, gallery_id: int, tags: Sequence[str]
    ) -> int:
        """Update local tags for a gallery."""
        async with self.transaction():
            gallery = await self.uow.galleries.get_by_id(gallery_id)
            if gallery is None:
                raise NotFoundError(f"Gallery {gallery_id} not found")
            return await self.uow.galleries.set_local_tags(gallery_id, tags)

    async def restore_galleries(self, gallery_ids: Sequence[int]) -> BatchOperationResult:
        """Restore trashed galleries back to active library."""
        valid_ids = [gid for gid in gallery_ids if gid is not None]
        if not valid_ids:
            return BatchOperationResult(total=0, succeeded=0, failed=0, errors=[])

        async with (
            self.audit_scope(
                task_type="restore_galleries",
                message=f"Restored {len(valid_ids)} galleries from trash",
                details={"ids": valid_ids},
            ),
            self.transaction(),
        ):
            restored_count = await self.uow.galleries.restore_galleries(valid_ids)

        return BatchOperationResult(
            total=len(valid_ids),
            succeeded=restored_count,
            failed=len(valid_ids) - restored_count,
            errors=[],
        )

    async def list_trashed(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> PageResponse[Any]:
        """Fetch paginated list of trashed galleries."""
        total, items = await self.uow.galleries.list_trashed(page, page_size)
        return PageResponse.create(
            items=items,
            total=total,
            params=PageParams(page=page, page_size=page_size),
        )

    async def list_expunged(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> PageResponse[Any]:
        """Fetch paginated list of expunged galleries."""
        total, items = await self.uow.galleries.list_expunged(page, page_size)
        return PageResponse.create(
            items=items,
            total=total,
            params=PageParams(page=page, page_size=page_size),
        )

    async def search_tags(
        self,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
        namespace: str | None = None,
    ) -> PageResponse[dict[str, Any]]:
        """Search tags by pattern and optional namespace filter."""
        total, items = await self.uow.galleries.search_tags(
            q=q, page=page, page_size=page_size, namespace=namespace
        )
        formatted = [
            {"namespace": ns, "name": name, "count": count}
            for ns, name, count in items
        ]
        return PageResponse.create(
            items=formatted,
            total=total,
            params=PageParams(page=page, page_size=page_size),
        )

    async def tag_facets(self) -> list[dict[str, Any]]:
        """Retrieve aggregated tag counts grouped by namespace."""
        facets = await self.uow.galleries.tag_facets()
        return [{"namespace": ns, "count": count} for ns, count in facets]

