from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ..config import Settings


def create_database(settings: Settings) -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)
