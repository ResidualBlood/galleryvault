"""Core application exceptions and domain error hierarchy."""

from __future__ import annotations

from typing import Any


class GalleryVaultError(Exception):
    """Base exception class for all GalleryVault domain and application errors."""

    def __init__(
        self,
        message: str = "An internal error occurred",
        *,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize error details for API responses."""
        payload: dict[str, Any] = {
            "detail": self.message,
            "code": self.code,
        }
        if self.details:
            payload["details"] = self.details
        return payload

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class DomainError(GalleryVaultError):
    """Domain model or business rule violation error."""

    def __init__(
        self,
        message: str = "Domain rule violation",
        *,
        code: str = "DOMAIN_ERROR",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class NotFoundError(GalleryVaultError):
    """Resource not found error."""

    def __init__(
        self,
        message: str | None = None,
        *,
        entity: str = "Resource",
        identifier: Any = None,
        code: str = "NOT_FOUND",
        status_code: int = 404,
        details: dict[str, Any] | None = None,
    ) -> None:
        if message is None:
            if identifier is not None:
                message = f"{entity} '{identifier}' not found"
            else:
                message = f"{entity} not found"
        merged_details = dict(details or {})
        merged_details["entity"] = entity
        if identifier is not None:
            merged_details["identifier"] = str(identifier)
        super().__init__(message, code=code, status_code=status_code, details=merged_details)


class ValidationError(GalleryVaultError):
    """Data validation or schema contract violation."""

    def __init__(
        self,
        message: str = "Validation failed",
        *,
        code: str = "VALIDATION_ERROR",
        status_code: int = 422,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class AuthenticationError(GalleryVaultError):
    """Authentication failure or invalid credentials."""

    def __init__(
        self,
        message: str = "Authentication required",
        *,
        code: str = "AUTHENTICATION_FAILED",
        status_code: int = 401,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class PermissionDeniedError(GalleryVaultError):
    """Permission denied or unauthorized access to resource."""

    def __init__(
        self,
        message: str = "Permission denied",
        *,
        code: str = "PERMISSION_DENIED",
        status_code: int = 403,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class ConflictError(GalleryVaultError):
    """Resource conflict or state collision."""

    def __init__(
        self,
        message: str = "Resource conflict occurred",
        *,
        code: str = "CONFLICT",
        status_code: int = 409,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class ServiceUnavailableError(GalleryVaultError):
    """External service or subsystem unavailable."""

    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        *,
        code: str = "SERVICE_UNAVAILABLE",
        status_code: int = 503,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class EhClientError(GalleryVaultError):
    """Generic E-Hentai / ExHentai remote client error."""

    def __init__(
        self,
        message: str = "E-Hentai service error",
        *,
        code: str = "EH_CLIENT_ERROR",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class EhClientUnavailableError(EhClientError):
    """E-Hentai client is not configured or uninitialized."""

    def __init__(
        self,
        message: str = "ExHentai client is unavailable or not configured",
        *,
        code: str = "EH_CLIENT_UNAVAILABLE",
        status_code: int = 503,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class EhQuotaExceededError(EhClientError):
    """E-Hentai image or API quota limit hit."""

    def __init__(
        self,
        message: str = "E-Hentai image limits exceeded",
        *,
        code: str = "EH_QUOTA_EXCEEDED",
        status_code: int = 429,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class DatabaseError(GalleryVaultError):
    """Database connectivity or query execution error."""

    def __init__(
        self,
        message: str = "Database operation failed",
        *,
        code: str = "DATABASE_ERROR",
        status_code: int = 503,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)


class TaskExecutionError(GalleryVaultError):
    """Background task failure or execution abortion."""

    def __init__(
        self,
        message: str = "Background task execution failed",
        *,
        code: str = "TASK_EXECUTION_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code, details=details)
