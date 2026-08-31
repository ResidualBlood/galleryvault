"""Unit of Work pattern implementation for database transactions and repositories."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from .repository import (
    BackgroundJobsRepository,
    DownloadRepository,
    FavoritesRepository,
    GalleryRepository,
    GalleryUpdatesRepository,
    SettingsRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class UnitOfWork:
    """Encapsulates a database transaction and provides convenient repository access."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._galleries: GalleryRepository | None = None
        self._downloads: DownloadRepository | None = None
        self._favorites: FavoritesRepository | None = None
        self._settings: SettingsRepository | None = None
        self._jobs: BackgroundJobsRepository | None = None
        self._updates: GalleryUpdatesRepository | None = None

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        await self.session.begin()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session is not None:
            try:
                if exc_type is not None:
                    await self.session.rollback()
                else:
                    await self.session.commit()
            finally:
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
