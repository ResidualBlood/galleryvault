"""Unit of Work interface and SQLAlchemy implementation."""

from __future__ import annotations

import abc
from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db.repositories.downloads import DownloadRepository
from ...db.repositories.favorites import FavoritesRepository
from ...db.repositories.galleries import GalleryRepository
from ...db.repositories.jobs import BackgroundJobsRepository
from ...db.repositories.lists import LocalListRepository
from ...db.repositories.series import SeriesRepository
from ...db.repositories.settings import SettingsRepository
from ...db.repositories.updates import GalleryUpdatesRepository
from ..exceptions import DatabaseError


class AbstractUnitOfWork(abc.ABC):
    """Abstract Base Class defining the Unit of Work interface."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()

    @property
    @abc.abstractmethod
    def session(self) -> AsyncSession:
        """Return the active database session."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def galleries(self) -> GalleryRepository:
        """Return the GalleryRepository instance."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def downloads(self) -> DownloadRepository:
        """Return the DownloadRepository instance."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def favorites(self) -> FavoritesRepository:
        """Return the FavoritesRepository instance."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def settings(self) -> SettingsRepository:
        """Return the SettingsRepository instance."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def jobs(self) -> BackgroundJobsRepository:
        """Return the BackgroundJobsRepository instance."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def updates(self) -> GalleryUpdatesRepository:
        """Return the GalleryUpdatesRepository instance."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def lists(self) -> LocalListRepository:
        """Return the LocalListRepository instance."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def series(self) -> SeriesRepository:
        """Return the SeriesRepository instance."""
        raise NotImplementedError

    @abc.abstractmethod
    async def commit(self) -> None:
        """Commit the current transaction."""
        raise NotImplementedError

    @abc.abstractmethod
    async def rollback(self) -> None:
        """Rollback the current transaction."""
        raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """SQLAlchemy-based Unit of Work managing session and transaction life cycle."""

    def __init__(
        self,
        session_or_factory: AsyncSession | async_sessionmaker[AsyncSession] | Callable[[], AsyncSession] | None = None,
        *,
        autocommit: bool = True,
    ) -> None:
        self._session_or_factory = session_or_factory
        self._session: AsyncSession | None = None
        self._owns_session = False
        self._autocommit = autocommit
        self._committed = False
        self._galleries: GalleryRepository | None = None
        self._downloads: DownloadRepository | None = None
        self._favorites: FavoritesRepository | None = None
        self._settings: SettingsRepository | None = None
        self._jobs: BackgroundJobsRepository | None = None
        self._updates: GalleryUpdatesRepository | None = None
        self._lists: LocalListRepository | None = None
        self._series: SeriesRepository | None = None

        if isinstance(session_or_factory, AsyncSession):
            self._session = session_or_factory
            self._owns_session = False

    @property
    def session(self) -> AsyncSession:
        """Get the active database session, raising if not in context or uninitialized."""
        if self._session is None:
            raise DatabaseError("UnitOfWork session is not active. Use 'async with uow:' context.")
        return self._session

    @property
    def galleries(self) -> GalleryRepository:
        """Return the GalleryRepository bound to current session."""
        if self._galleries is None:
            self._galleries = GalleryRepository(self.session)
        return self._galleries

    @property
    def downloads(self) -> DownloadRepository:
        """Return the DownloadRepository bound to current session."""
        if self._downloads is None:
            self._downloads = DownloadRepository(self.session)
        return self._downloads

    @property
    def favorites(self) -> FavoritesRepository:
        """Return the FavoritesRepository bound to current session."""
        if self._favorites is None:
            self._favorites = FavoritesRepository(self.session)
        return self._favorites

    @property
    def settings(self) -> SettingsRepository:
        """Return the SettingsRepository bound to current session."""
        if self._settings is None:
            self._settings = SettingsRepository(self.session)
        return self._settings

    @property
    def jobs(self) -> BackgroundJobsRepository:
        """Return the BackgroundJobsRepository bound to current session."""
        if self._jobs is None:
            self._jobs = BackgroundJobsRepository(self.session)
        return self._jobs

    @property
    def updates(self) -> GalleryUpdatesRepository:
        """Return the GalleryUpdatesRepository bound to current session."""
        if self._updates is None:
            self._updates = GalleryUpdatesRepository(self.session)
        return self._updates

    @property
    def lists(self) -> LocalListRepository:
        """Return the LocalListRepository bound to current session."""
        if self._lists is None:
            self._lists = LocalListRepository(self.session)
        return self._lists

    @property
    def series(self) -> SeriesRepository:
        """Return the SeriesRepository bound to current session."""
        if self._series is None:
            self._series = SeriesRepository(self.session)
        return self._series

    async def __aenter__(self) -> Self:
        self._committed = False
        if self._session is None and self._session_or_factory is not None:
            # Create session from factory
            res = self._session_or_factory()
            if hasattr(res, "__aenter__"):
                self._session = await res.__aenter__()
            else:
                self._session = res
            self._owns_session = True
        return self

    async def commit(self) -> None:
        """Explicitly commit the transaction."""
        if self._session is not None and not self._committed:
            try:
                await self._session.commit()
                self._committed = True
            except Exception as exc:
                await self.rollback()
                raise DatabaseError(f"Commit failed: {exc}") from exc

    async def rollback(self) -> None:
        """Explicitly rollback the transaction."""
        if self._session is not None:
            try:
                await self._session.rollback()
            except Exception:  # noqa: BLE001, S110
                pass

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
            elif self._autocommit and not self._committed:
                await self.commit()
        finally:
            if self._owns_session and self._session is not None:
                try:
                    if hasattr(self._session, "aclose"):
                        await self._session.aclose()
                    elif hasattr(self._session, "close"):
                        res = self._session.close()
                        if hasattr(res, "__await__"):
                            await res
                finally:
                    self._session = None
                    self._galleries = None
                    self._downloads = None
                    self._favorites = None
                    self._settings = None
                    self._jobs = None
                    self._updates = None
                    self._lists = None
                    self._series = None


# Compatibility alias
UnitOfWork = SqlAlchemyUnitOfWork
