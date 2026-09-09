import hashlib
from abc import ABC
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Generic, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession


def path_hash(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()


# asyncpg binds ~32767 parameters per statement; every ``column.in_(...)`` with
# a caller-supplied list must go through this to stay under the limit.
_CHUNK_SIZE = 500


def escape_like_wildcards(val: str) -> str:
    """Escape SQL LIKE/ILIKE wildcards (%, _, \\) to treat user input as literal text."""
    return val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _chunked(values: Sequence[Any], size: int = _CHUNK_SIZE) -> list[list[Any]]:
    """Split ``values`` into fixed-size slices for ``in_``-style queries."""
    values_list = list(values)
    return [values_list[start : start + size] for start in range(0, len(values_list), size)]


ModelT = TypeVar("ModelT")


class BaseRepository(ABC, Generic[ModelT]):  # noqa: UP046
    """Generic repository base class providing standard CRUD, batch, pagination, and count operations."""

    def __init__(
        self,
        session: AsyncSession,
        model_cls: type[ModelT] | None = None,
    ) -> None:
        self.session = session
        self.model_cls = model_cls

    def _require_model_cls(self) -> type[ModelT]:
        if self.model_cls is None:
            raise ValueError(f"model_cls is not configured for {self.__class__.__name__}")
        return self.model_cls

    async def get_by_id(self, id_val: Any) -> ModelT | None:
        """Fetch single model entity by primary key."""
        model_cls = self._require_model_cls()
        return await self.session.get(model_cls, id_val)

    async def get_by_ids(
        self, ids: Sequence[Any], id_attr: str = "id"
    ) -> list[ModelT]:
        """Fetch multiple model entities by list of IDs using batch chunks."""
        valid_ids = [i for i in ids if i is not None]
        if not valid_ids:
            return []
        model_cls = self._require_model_cls()
        column = getattr(model_cls, id_attr)
        results: list[ModelT] = []
        for chunk in _chunked(valid_ids):
            stmt = select(model_cls).where(column.in_(chunk))
            rows = await self.session.scalars(stmt)
            results.extend(rows.all())
        return results

    def add(self, entity: ModelT) -> ModelT:
        """Add new entity to session."""
        self.session.add(entity)
        return entity

    def add_many(self, entities: Sequence[ModelT]) -> None:
        """Add multiple entities to session."""
        self.session.add_all(entities)

    async def delete(self, entity: ModelT) -> None:
        """Delete an entity from session."""
        await self.session.delete(entity)

    async def delete_by_id(self, id_val: Any) -> bool:
        """Fetch entity by id and delete it. Returns True if deleted, False if not found."""
        entity = await self.get_by_id(id_val)
        if entity is None:
            return False
        await self.delete(entity)
        return True

    async def delete_by_ids(
        self, ids: Sequence[Any], id_attr: str = "id"
    ) -> int:
        """Batch delete entities by IDs."""
        valid_ids = [i for i in ids if i is not None]
        if not valid_ids:
            return 0
        model_cls = self._require_model_cls()
        column = getattr(model_cls, id_attr)
        deleted_count = 0
        for chunk in _chunked(valid_ids):
            stmt = delete(model_cls).where(column.in_(chunk))
            result = await self.session.execute(stmt)
            deleted_count += int(result.rowcount or 0)
        return deleted_count

    async def count(self, *predicates: Any) -> int:
        """Count rows matching given predicates."""
        model_cls = self._require_model_cls()
        stmt = select(func.count()).select_from(model_cls)
        if predicates:
            stmt = stmt.where(*predicates)
        result = await self.session.scalar(stmt)
        return int(result or 0)

    async def list_all(
        self,
        *predicates: Any,
        order_by: Sequence[Any] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ModelT]:
        """Query all entities matching optional predicates and order."""
        model_cls = self._require_model_cls()
        stmt = select(model_cls)
        if predicates:
            stmt = stmt.where(*predicates)
        if order_by:
            stmt = stmt.order_by(*order_by)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = await self.session.scalars(stmt)
        return list(rows.all())

    async def list_paged(
        self,
        page: int,
        page_size: int,
        *predicates: Any,
        order_by: Sequence[Any] | None = None,
    ) -> tuple[int, list[ModelT]]:
        """Paginated query returning (total_count, items)."""
        total = await self.count(*predicates)
        offset = max(0, (page - 1) * page_size)
        items = await self.list_all(
            *predicates, order_by=order_by, limit=page_size, offset=offset
        )
        return total, items

    async def flush(self) -> None:
        """Flush pending changes to database."""
        await self.session.flush()

