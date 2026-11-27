import logging
from collections.abc import Sequence

from ..app.core.eh_client_manager import EhClientManager
from ..app.core.task_dispatcher import TaskDispatcher
from ..app.core.uow import UnitOfWork
from ..app.dependencies import BatchOperationResult
from ..app.exceptions import NotFoundError
from ..db.models import FavoritesMonitor
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
                        cloud_failed = await client.move_favorites(
                            valid_gids, target_favcat
                        )
                        if isinstance(cloud_failed, (list, set, tuple)):
                            # The client returns the gids it could NOT move.
                            failed_set = {int(g) for g in cloud_failed}
                            successful_gids = [
                                g for g in valid_gids if g not in failed_set
                            ]
                            errors.extend(
                                f"Cloud move failed for {g}" for g in sorted(failed_set)
                            )
                        elif cloud_failed is False:
                            successful_gids = []
                            errors.append("Cloud operation rejected")
                        else:
                            successful_gids = []
                            errors.append("Cloud move result was not understood")
                    else:
                        successful_gids = []
                        errors.append("EhClient cannot move favorites")
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
                        cloud_failed = await client.remove_favorites(valid_gids)
                        if isinstance(cloud_failed, (list, set, tuple)):
                            # The client returns the gids it could NOT remove.
                            failed_set = {int(g) for g in cloud_failed}
                            successful_gids = [
                                g for g in valid_gids if g not in failed_set
                            ]
                            errors.extend(
                                f"Cloud removal failed for {g}" for g in sorted(failed_set)
                            )
                        elif cloud_failed is False:
                            successful_gids = []
                            errors.append("Cloud removal rejected")
                        else:
                            successful_gids = []
                            errors.append("Cloud removal result was not understood")
                    else:
                        successful_gids = []
                        errors.append("EhClient cannot remove favorites")
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
        """Update note for a favorite gallery, cloud first then DB.

        ExHentai has no dedicated note endpoint: notes are written through the
        same ``gallerypopups.php?act=addfav`` form as adding a favorite
        (``add_favorite(..., note=...)``).  The local note must never be
        written before the cloud confirms it.
        """
        item = await self.uow.favorites.item_for_gid(int(gid))
        if item is None:
            return False

        if (
            sync_cloud
            and self.eh_client_manager is not None
            and self.eh_client_manager.is_configured()
        ):
            token = getattr(item, "token", None)
            if not token:
                self.logger.warning(
                    "Cannot sync favorite note %s to cloud: missing token", gid
                )
                return False
            target_favcat = int(favcat if favcat is not None else item.favcat)
            try:
                async with self.eh_client_manager.client_context() as client:
                    add_favorite = getattr(client, "add_favorite", None)
                    if add_favorite is None:
                        self.logger.warning(
                            "EhClient cannot update favorite notes; cloud note not synced"
                        )
                        return False
                    await add_favorite(int(gid), str(token), target_favcat, note=note)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Failed to sync favorite note to cloud: %s", exc)
                return False

        async with self.transaction():
            affected = await self.uow.favorites.update_note(gid, note, favcat=favcat)

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
