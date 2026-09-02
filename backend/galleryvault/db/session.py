from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ..config import Settings


def create_database(settings: Settings) -> tuple[AsyncEngine, async_sessionmaker]:
    # Explicit pool sizing: the default asyncpg pool is only 5+10 connections,
    # while tag-sync / thumbnail / download workers each hold connections open
    # across network I/O. pool_recycle < PostgreSQL's idle timeout keeps stale
    # connections from lingering, and pool_pre_ping avoids handing out dead ones.
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=10,
        pool_recycle=3600,
        pool_timeout=30,
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)
