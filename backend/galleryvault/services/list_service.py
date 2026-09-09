"""Business service for local custom lists management and gallery associations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..app.exceptions import ConflictError, NotFoundError, ValidationError
from .base_service import BaseService

if TYPE_CHECKING:
    from ..app.core.task_dispatcher import TaskDispatcher
    from ..app.core.uow import UnitOfWork

logger = logging.getLogger(__name__)


class ListService(BaseService):
    """Business service governing user-defined lists, membership, and sorting."""

    def __init__(
        self,
        uow: UnitOfWork | None = None,
        task_dispatcher: TaskDispatcher | None = None,
    ) -> None:
        super().__init__(uow=uow, task_dispatcher=task_dispatcher)

    async def list_all_lists(self) -> list[dict[str, Any]]:
        """Retrieve all local lists with their gallery counts."""
        async with self.transaction():
            rows = await self.uow.lists.list_all()
            return [
                {
                    "id": item.id,
                    "name": item.name,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "gallery_count": count,
                }
                for item, count in rows
            ]

    async def get_list_detail(self, list_id: int) -> dict[str, Any]:
        """Fetch list details including member galleries."""
        async with self.transaction():
            local_list = await self.uow.lists.get(list_id)
            if local_list is None:
                raise NotFoundError(f"List {list_id} not found", entity="LocalList", entity_id=list_id)

            galleries = await self.uow.lists.get_items_with_galleries(list_id)
            return {
                "id": local_list.id,
                "name": local_list.name,
                "created_at": local_list.created_at.isoformat() if local_list.created_at else None,
                "gallery_count": len(galleries),
                "items": [
                    {
                        "id": g.id,
                        "gid": g.gid,
                        "title": g.title,
                        "title_jpn": g.title_jpn,
                        "category": g.category,
                        "page_count": g.page_count,
                        "cover_path": g.cover_path,
                        "rating": g.rating,
                        "favcat": getattr(g, "favcat", None),
                    }
                    for g in galleries
                ],
            }

    async def create_list(self, name: str) -> dict[str, Any]:
        """Create a new local list with unique name validation."""
        clean_name = name.strip() if name else ""
        if not clean_name:
            raise ValidationError("List name cannot be empty", field="name")

        async with self.transaction():
            existing = await self.uow.lists.get_by_name(clean_name)
            if existing is not None:
                raise ConflictError(
                    f"List with name '{clean_name}' already exists",
                    entity="LocalList",
                    entity_id=existing.id,
                )

            new_list = await self.uow.lists.create(clean_name)
            return {
                "id": new_list.id,
                "name": new_list.name,
                "created_at": new_list.created_at.isoformat() if new_list.created_at else None,
                "gallery_count": 0,
            }

    async def rename_list(self, list_id: int, name: str) -> dict[str, Any]:
        """Rename an existing local list."""
        clean_name = name.strip() if name else ""
        if not clean_name:
            raise ValidationError("List name cannot be empty", field="name")

        async with self.transaction():
            existing = await self.uow.lists.get_by_name(clean_name)
            if existing is not None and existing.id != list_id:
                raise ConflictError(
                    f"Another list named '{clean_name}' already exists",
                    entity="LocalList",
                    entity_id=existing.id,
                )

            updated = await self.uow.lists.rename(list_id, clean_name)
            if updated is None:
                raise NotFoundError(f"List {list_id} not found", entity="LocalList", entity_id=list_id)

            return {
                "id": updated.id,
                "name": updated.name,
                "created_at": updated.created_at.isoformat() if updated.created_at else None,
            }

    async def delete_list(self, list_id: int) -> bool:
        """Delete a local list and all its associations."""
        async with self.transaction():
            deleted = await self.uow.lists.delete_list(list_id)
            if not deleted:
                raise NotFoundError(f"List {list_id} not found", entity="LocalList", entity_id=list_id)
            return True

    async def add_galleries_to_list(self, list_id: int, gallery_ids: list[int]) -> int:
        """Associate galleries with a local list."""
        if not gallery_ids:
            return 0

        async with self.transaction():
            local_list = await self.uow.lists.get(list_id)
            if local_list is None:
                raise NotFoundError(f"List {list_id} not found", entity="LocalList", entity_id=list_id)

            added_count = await self.uow.lists.add_items(list_id, gallery_ids)

        if self.task_dispatcher and added_count > 0:
            await self.record_task_audit(
                action="list_add_galleries",
                target=f"list:{list_id}",
                status="success",
                message=f"Added {added_count} galleries to list {list_id}",
                details={"added_count": added_count, "gallery_ids": gallery_ids},
            )

        return added_count

    async def remove_galleries_from_list(self, list_id: int, gallery_ids: list[int]) -> int:
        """Disassociate galleries from a local list."""
        if not gallery_ids:
            return 0

        async with self.transaction():
            local_list = await self.uow.lists.get(list_id)
            if local_list is None:
                raise NotFoundError(f"List {list_id} not found", entity="LocalList", entity_id=list_id)

            removed_count = await self.uow.lists.remove_items(list_id, gallery_ids)

        if self.task_dispatcher and removed_count > 0:
            await self.record_task_audit(
                action="list_remove_galleries",
                target=f"list:{list_id}",
                status="success",
                message=f"Removed {removed_count} galleries from list {list_id}",
                details={"removed_count": removed_count, "gallery_ids": gallery_ids},
            )

        return removed_count

    async def get_lists_for_gallery(self, gallery_id: int) -> list[dict[str, Any]]:
        """Retrieve all lists containing the specified gallery."""
        async with self.transaction():
            lists = await self.uow.lists.lists_for_gallery(gallery_id)
            return [
                {
                    "id": lst.id,
                    "name": lst.name,
                    "created_at": lst.created_at.isoformat() if lst.created_at else None,
                }
                for lst in lists
            ]
