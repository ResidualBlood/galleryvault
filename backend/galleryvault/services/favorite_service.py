import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ..app.core.eh_client_manager import EhClientManager
from ..app.core.task_dispatcher import TaskDispatcher
from ..app.core.uow import UnitOfWork
from ..app.dependencies import BatchOperationResult, PageParams, PageResponse
from ..app.exceptions import NotFoundError
from ..db.models import FavoritesCheckLog, FavoritesMonitor
from .base_service import BaseService


class FavoriteService(BaseService):
    """Service orchestrating favorite folders, item management,

    dual-state synchronization with ExHentai, and consistency guarantees.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        task_dispatcher: TaskDispatcher | None = None,
        eh_client_manager: EhClientManager | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(uow, task_dispatcher, logger)
        self.eh_client_manager = eh_client_manager

    async def list_categories(self) -> list[FavoritesMonitor]:
        """Fetch all monitored favorite folder categories."""
        return await self.uow.favorites.list_categories()

    async def get_category(self, favcat: int) -> FavoritesMonitor:
        """Fetch single favorite category monitor; raises NotFoundError if missing."""
        monitor = await self.uow.favorites.get_category(favcat)
        if monitor is None:
            raise NotFoundError(f"Favorite category {favcat} not found")
        return monitor

    async def get_category_stats(self) -> list[dict[str, Any]]:
        """Compute comprehensive stats per favorite folder."""
        counts = await self.uow.favorites.counts_and_sizes()
        categories = await self.uow.favorites.list_categories()
        cat_map = {c.favcat: c for c in categories}

        result: list[dict[str, Any]] = []
        for favcat in range(10):  # 0 to 9 standard favcats
            cloud_count, local_count, local_bytes = counts.get(favcat, (0, 0, 0))
            monitor = cat_map.get(favcat)
            result.append(
                {
                    "favcat": favcat,
                    "name": monitor.name if monitor else f"Favorite {favcat}",
                    "enabled": monitor.enabled if monitor else False,
                    "last_checked_at": monitor.last_checked_at if monitor else None,
                    "last_success_at": monitor.last_success_at if monitor else None,
                    "cloud_count": cloud_count,
                    "local_count": local_count,
                    "local_bytes": local_bytes,
                }
            )
        return result

    async def list_favorites(
        self,
        favcat: int,
        page_params: PageParams | None = None,
        page: int | None = None,
        page_size: int | None = None,
        state: str = "all",
        q: str | None = None,
        order_by: str = "last_seen_desc",
        category: str | None = None,
        tags: Sequence[tuple[str | None, str]] = (),
        exclude_tags: Sequence[tuple[str | None, str]] = (),
        tag_mode: str = "and",
        tag_match: str = "exact",
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
    ) -> PageResponse[dict[str, Any]]:
        """Fetch paginated favorite items with joined gallery info and tags."""
        actual_page = page or (page_params.page if page_params else 1)
        actual_page_size = page_size or (page_params.page_size if page_params else 50)

        tag_id_map = None
        if tags or exclude_tags:
            all_tags = list(tags) + list(exclude_tags)
            tag_id_map = await self.uow.galleries.resolve_exact_tags(all_tags)

        total, raw_items = await self.uow.favorites.list_items(
            favcat=favcat,
            page=actual_page,
            page_size=actual_page_size,
            state=state,
            q=q,
            order_by=order_by,
            category=category,
            tags=tags,
            exclude_tags=exclude_tags,
            tag_mode=tag_mode,
            tag_match=tag_match,
            tag_id_map=tag_id_map,
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
        )

        # Batch load tags for present local galleries
        local_ids = [
            gallery.id
            for _, gallery in raw_items
            if gallery is not None and getattr(gallery, "id", None) is not None
        ]
        tags_map = await self.uow.favorites.tags_for_gallery_ids(local_ids)

        formatted_items: list[dict[str, Any]] = []
        for fav_item, gallery in raw_items:
            gid = getattr(fav_item, "gid", None)
            token = getattr(fav_item, "token", None) or (
                getattr(gallery, "token", None) if gallery else None
            )
            title = getattr(fav_item, "title", None) or (
                getattr(gallery, "title", None) if gallery else None
            )
            g_id = getattr(gallery, "id", None) if gallery else None
            page_count = getattr(gallery, "page_count", None) if gallery else None

            formatted_items.append(
                {
                    "gid": gid,
                    "favcat": getattr(fav_item, "favcat", favcat),
                    "token": token,
                    "title": title,
                    "url": getattr(fav_item, "url", None),
                    "thumb": getattr(fav_item, "thumb", None),
                    "note": getattr(fav_item, "note", None),
                    "first_seen_at": getattr(fav_item, "first_seen_at", None),
                    "last_seen_at": getattr(fav_item, "last_seen_at", None),
                    "gallery_id": g_id,
                    "is_local": gallery is not None,
                    "category": (
                        getattr(gallery, "category", None) if gallery else None
                    ),
                    "page_count": page_count,
                    "cover_url": (
                        f"/api/galleries/{g_id}/thumb/0"
                        if g_id and page_count
                        else None
                    ),
                    "file_size": (
                        getattr(gallery, "file_size", None)
                        if gallery and getattr(gallery, "file_size", None) is not None
                        else getattr(fav_item, "file_size", None)
                    ),
                    "posted_at": (
                        getattr(gallery, "posted_at", None) if gallery else None
                    ),
                    "tags": [
                        {"namespace": ns, "name": name}
                        for ns, name in tags_map.get(g_id or -1, [])
                    ],
                }
            )

        return PageResponse.create(
            items=formatted_items,
            total=total,
            params=PageParams(page=actual_page, page_size=actual_page_size),
        )

    async def move_favorites(
        self,
        gids: Sequence[int],
        target_favcat: int,
        sync_cloud: bool = True,
    ) -> BatchOperationResult:
        """Move favorite items to a target folder, respecting ExHentai dual-state consistency."""
        valid_gids = list(dict.fromkeys([int(g) for g in gids if g is not None]))
        if not valid_gids:
            return BatchOperationResult(total=0, succeeded=0, failed=0, errors=[])

        successful_gids: list[int] = []
        errors: list[str] = []

        # Dual-state check: Cloud first if enabled and configured
        if (
            sync_cloud
            and self.eh_client_manager is not None
            and self.eh_client_manager.is_configured()
        ):
            try:
                async with self.eh_client_manager.client_context() as client:
                    if hasattr(client, "move_favorites"):
                        cloud_res = await client.move_favorites(
                            valid_gids, target_favcat
                        )
                        if isinstance(cloud_res, (list, set, tuple)):
                            successful_gids = [int(g) for g in cloud_res]
                        elif cloud_res is False:
                            successful_gids = []
                            errors.append("Cloud operation rejected")
                        else:
                            successful_gids = valid_gids
                    else:
                        successful_gids = valid_gids
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Cloud move_favorites failed: %s", exc)
                errors.append(f"Cloud synchronization failed: {exc}")
                successful_gids = []
        else:
            successful_gids = valid_gids

        # Update local DB only for confirmed successful gids
        if successful_gids:
            async with (
                self.audit_scope(
                    task_type="move_favorites",
                    message=f"Moved {len(successful_gids)} items to favcat {target_favcat}",
                    details={"gids": successful_gids, "target_favcat": target_favcat},
                ),
                self.transaction(),
            ):
                await self.uow.favorites.move_gids(
                    successful_gids, target_favcat
                )

        failed_count = len(valid_gids) - len(successful_gids)
        return BatchOperationResult(
            total=len(valid_gids),
            succeeded=len(successful_gids),
            failed=failed_count,
            errors=errors,
        )

    async def remove_favorites(
        self,
        gids: Sequence[int],
        favcat: int | None = None,
        sync_cloud: bool = True,
    ) -> BatchOperationResult:
        """Remove favorites locally and from cloud, maintaining dual-state consistency."""
        valid_gids = list(dict.fromkeys([int(g) for g in gids if g is not None]))
        if not valid_gids:
            return BatchOperationResult(total=0, succeeded=0, failed=0, errors=[])

        successful_gids: list[int] = []
        errors: list[str] = []

        if (
            sync_cloud
            and self.eh_client_manager is not None
            and self.eh_client_manager.is_configured()
        ):
            try:
                async with self.eh_client_manager.client_context() as client:
                    if hasattr(client, "remove_favorites"):
                        cloud_res = await client.remove_favorites(valid_gids)
                        if isinstance(cloud_res, (list, set, tuple)):
                            successful_gids = [int(g) for g in cloud_res]
                        elif cloud_res is False:
                            successful_gids = []
                            errors.append("Cloud removal rejected")
                        else:
                            successful_gids = valid_gids
                    else:
                        successful_gids = valid_gids
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Cloud remove_favorites failed: %s", exc)
                errors.append(f"Cloud synchronization failed: {exc}")
                successful_gids = []
        else:
            successful_gids = valid_gids

        # Update local DB only for confirmed items
        if successful_gids:
            async with (
                self.audit_scope(
                    task_type="remove_favorites",
                    message=f"Removed {len(successful_gids)} favorite items",
                    details={"gids": successful_gids, "favcat": favcat},
                ),
                self.transaction(),
            ):
                await self.uow.favorites.remove_gids(
                    successful_gids
                )

        failed_count = len(valid_gids) - len(successful_gids)
        return BatchOperationResult(
            total=len(valid_gids),
            succeeded=len(successful_gids),
            failed=failed_count,
            errors=errors,
        )

    async def update_note(
        self,
        gid: int,
        note: str,
        favcat: int | None = None,
        sync_cloud: bool = True,
    ) -> bool:
        """Update note for a favorite gallery in DB and optionally on cloud."""
        async with self.transaction():
            affected = await self.uow.favorites.update_note(gid, note, favcat=favcat)

        if (
            sync_cloud
            and affected > 0
            and self.eh_client_manager is not None
            and self.eh_client_manager.is_configured()
        ):
            try:
                async with self.eh_client_manager.client_context() as client:
                    if hasattr(client, "update_favorite_note"):
                        await client.update_favorite_note(gid, note, favcat=favcat)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Failed to sync favorite note to cloud: %s", exc)

        return affected > 0

    async def upsert_category(
        self,
        favcat: int,
        name: str | None = None,
        enabled: bool | None = None,
    ) -> FavoritesMonitor:
        """Create or update favorite monitor configuration."""
        async with self.transaction():
            return await self.uow.favorites.upsert_category(
                favcat=favcat, name=name, enabled=enabled
            )

    async def delete_category(self, favcat: int, delete_items: bool = True) -> bool:
        """Delete favorite monitor configuration and optionally delete folder items."""
        async with self.transaction():
            return await self.uow.favorites.delete_category(
                favcat=favcat, delete_items=delete_items
            )

    async def cloud_size_breakdown(self, favcat: int) -> dict[str, int]:
        """Fetch estimated cloud size metrics for a favorite folder."""
        known_bytes, unknown_count = await self.uow.favorites.cloud_size_breakdown(
            favcat
        )
        return {
            "known_bytes": known_bytes,
            "unknown_count": unknown_count,
        }

    async def list_check_logs(
        self, favcat: int | None = None, limit: int = 50
    ) -> list[FavoritesCheckLog]:
        """Fetch historical folder check logs."""
        return await self.uow.favorites.list_logs(favcat=favcat, limit=limit)
