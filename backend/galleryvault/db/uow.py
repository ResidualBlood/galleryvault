"""Unit of Work pattern implementation for database transactions and repositories."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Self

from sqlalchemy.ext.asyncio import AsyncSession

from .repository import (
    BackgroundJobsRepository,
    DownloadRepository,
    FavoritesRepository,
    GalleryRepository,
    GalleryUpdatesRepository,
    SettingsRepository,
)


class UnitOfWork:
    """Encapsulates a database transaction and provides convenient repository access."""

    def __init__(
        self,
        session_or_factory: Any,
    ) -> None:
        # Use isinstance check first to avoid misclassifying AsyncSession subclasses or
        # Session-factory wrappers that expose ``begin``.
        if isinstance(session_or_factory, AsyncSession):
            self._session_factory: Callable[[], Any] | None = None
            self.session: Any = session_or_factory
            self._external_session = True
        elif callable(session_or_factory):
            self._session_factory = session_or_factory
            self.session = None
            self._external_session = False
        else:
            # Duck-typed session (e.g. FakeAsyncSession in tests) with commit/rollback
            has_session_api = hasattr(session_or_factory, "commit") and hasattr(
                session_or_factory, "rollback"
            )
            if has_session_api:
                self._session_factory = None
                self.session = session_or_factory
                self._external_session = True
            else:
                # Fallback to treating as external session
                self._session_factory = None
                self.session = session_or_factory
                self._external_session = True
        self._began = False
        self._galleries: GalleryRepository | None = None
        self._downloads: DownloadRepository | None = None
        self._favorites: FavoritesRepository | None = None
        self._settings: SettingsRepository | None = None
        self._jobs: BackgroundJobsRepository | None = None
        self._updates: GalleryUpdatesRepository | None = None

    @classmethod
    def from_factory(cls, factory: Callable[[], Any]) -> Self:
        return cls(factory)

    @classmethod
    def from_session(cls, session: Any) -> Self:
        return cls(session)

    async def __aenter__(self) -> Self:
        if self._session_factory is not None:
            self.session = self._session_factory()
            if hasattr(self.session, "begin"):
                await self.session.begin()
                self._began = True
        elif self.session is not None:
            in_tx = getattr(self.session, "in_transaction", None)
            should_begin = False
            if callable(in_tx):
                try:
                    should_begin = not in_tx()
                except Exception:  # noqa: BLE001
                    should_begin = True
            else:
                # No transaction introspection — assume we should begin
                should_begin = True
            if should_begin and hasattr(self.session, "begin"):
                await self.session.begin()
                self._began = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session is not None:
            try:
                if exc_type is not None and hasattr(self.session, "rollback"):
                    await self.session.rollback()
                elif self._began and hasattr(self.session, "commit"):
                    await self.session.commit()
                elif not self._external_session and hasattr(self.session, "commit"):
                    # Factory-owned session that didn't explicitly begin (e.g. no begin attr)
                    await self.session.commit()
            finally:
                if not self._external_session and hasattr(self.session, "close"):
                    await self.session.close()

    async def commit(self) -> None:
        if self.session is not None:
            await self.session.commit()

    async def rollback(self) -> None:
        if self.session is not None:
            await self.session.rollback()

    @property
    def galleries(self) -> GalleryRepository:
        if self.session is None:
            raise RuntimeError("UnitOfWork session is not active (must be used within 'async with')")
        if self._galleries is None:
            self._galleries = GalleryRepository(self.session)
        return self._galleries

    @property
    def downloads(self) -> DownloadRepository:
        if self.session is None:
            raise RuntimeError("UnitOfWork session is not active")
        if self._downloads is None:
            self._downloads = DownloadRepository(self.session)
        return self._downloads

    @property
    def favorites(self) -> FavoritesRepository:
        if self.session is None:
            raise RuntimeError("UnitOfWork session is not active")
        if self._favorites is None:
            self._favorites = FavoritesRepository(self.session)
        return self._favorites

    @property
    def settings(self) -> SettingsRepository:
        if self.session is None:
            raise RuntimeError("UnitOfWork session is not active")
        if self._settings is None:
            self._settings = SettingsRepository(self.session)
        return self._settings

    @property
    def jobs(self) -> BackgroundJobsRepository:
        if self.session is None:
            raise RuntimeError("UnitOfWork session is not active")
        if self._jobs is None:
            self._jobs = BackgroundJobsRepository(self.session)
        return self._jobs

    @property
    def updates(self) -> GalleryUpdatesRepository:
        if self.session is None:
            raise RuntimeError("UnitOfWork session is not active")
        if self._updates is None:
            self._updates = GalleryUpdatesRepository(self.session)
        return self._updates
