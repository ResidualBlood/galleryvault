"""Common schemas, generic pagination models and DTOs."""

from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class SortDirection(str, Enum):
    """Sort direction enumeration."""

    ASC = "asc"
    DESC = "desc"


class SortParams(BaseModel):
    """Sorting parameters."""

    model_config = ConfigDict(extra="ignore")

    order_by: str | None = Field(default=None, description="Field name to order by")
    direction: SortDirection = Field(
        default=SortDirection.ASC,
        description="Sort direction (asc or desc)",
    )


class PageParams(BaseModel):
    """Pagination query parameters."""

    model_config = ConfigDict(extra="ignore")

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=50, ge=1, le=500, description="Items per page")

    @property
    def offset(self) -> int:
        """Calculate SQL offset from page and page_size."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Alias for page_size for SQL limit."""
        return self.page_size


class PageResponse(BaseModel, Generic[T]):  # noqa: UP046
    """Generic pagination response envelope."""

    model_config = ConfigDict(extra="ignore")

    items: list[T] = Field(default_factory=list, description="List of items for current page")
    total: int = Field(default=0, ge=0, description="Total count of items across all pages")
    page: int = Field(default=1, ge=1, description="Current page number")
    page_size: int = Field(default=50, ge=1, description="Number of items per page")
    pages: int = Field(default=0, ge=0, description="Total number of pages")

    @classmethod
    def create(cls, items: list[T], total: int, params: PageParams) -> PageResponse[T]:
        """Construct PageResponse from items list, total count, and PageParams."""
        pages = (total + params.page_size - 1) // params.page_size if params.page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            pages=pages,
        )


class MessageResponse(BaseModel):
    """Standard message response DTO."""

    model_config = ConfigDict(extra="ignore")

    detail: str = Field(default="ok", description="Status or result message")
    success: bool = Field(default=True, description="Whether the operation succeeded")


class StatusResponse(BaseModel):
    """Standard status response DTO."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field(default="ok", description="Status code or summary")
    message: str | None = Field(default=None, description="Optional informational message")


class EntityIdResponse(BaseModel):
    """Identifier response for created or updated entities."""

    model_config = ConfigDict(extra="ignore")

    id: int | str = Field(description="Unique identifier of the entity")


class BatchOperationResult(BaseModel):
    """Generic summary result for batch operations."""

    model_config = ConfigDict(extra="ignore")

    total: int = Field(default=0, ge=0, description="Total operations attempted")
    succeeded: int = Field(default=0, ge=0, description="Count of successful operations")
    failed: int = Field(default=0, ge=0, description="Count of failed operations")
    errors: list[str] = Field(default_factory=list, description="Error messages encountered")
