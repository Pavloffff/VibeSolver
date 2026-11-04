from collections.abc import AsyncGenerator

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.adapter.config import get_settings

ASYNC_DSN_PREFIX = "postgresql+psycopg_async://"
SYNC_DSN_PREFIX = "postgresql+psycopg://"


def to_async_dsn(dsn: str) -> str:
    if dsn.startswith("postgresql://"):
        return ASYNC_DSN_PREFIX + dsn[len("postgresql://") :]
    if dsn.startswith("postgresql+psycopg://"):
        return ASYNC_DSN_PREFIX + dsn[len("postgresql+psycopg://") :]
    return dsn


def to_sync_dsn(dsn: str) -> str:
    if dsn.startswith("postgresql://"):
        return SYNC_DSN_PREFIX + dsn[len("postgresql://") :]
    if dsn.startswith("postgresql+psycopg_async://"):
        return SYNC_DSN_PREFIX + dsn[len("postgresql+psycopg_async://") :]
    return dsn


def create_db_engine() -> AsyncEngine:
    return create_async_engine(to_async_dsn(get_settings().database_url))


def create_sync_db_engine() -> Engine:
    return create_engine(to_sync_dsn(get_settings().database_url))


_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(bind=create_db_engine(), expire_on_commit=False)
    return _async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_async_session_factory()
    async with factory() as session:
        yield session
