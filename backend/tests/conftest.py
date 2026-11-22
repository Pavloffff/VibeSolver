import asyncio
import json
import os
import sys
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.adapter.db import get_session, to_async_dsn
from app.handler.app import create_app

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

API_BASE_URL = "http://test"


@pytest.fixture(scope="session")
def test_database_dsn() -> str:
    dsn = os.environ.get("VIBESOLVER_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("set VIBESOLVER_TEST_DATABASE_URL to a disposable migrated database")
    return dsn


@pytest.fixture
async def db_engine(test_database_dsn: str) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(to_async_dsn(test_database_dsn), poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_database(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(text("TRUNCATE TABLE sources CASCADE"))


@pytest.fixture
async def api_client(request: pytest.FixtureRequest) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def test_session() -> AsyncGenerator[AsyncSession, None]:
        dsn = request.getfixturevalue("test_database_dsn")
        engine = create_async_engine(to_async_dsn(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                yield session
        finally:
            await engine.dispose()

    app.dependency_overrides[get_session] = test_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=API_BASE_URL) as client:
        yield client


@pytest.fixture
async def git_source_id(db_engine: AsyncEngine, clean_database: None) -> int:
    async with db_engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO sources (type, name, config) "
                "VALUES (:source_type, :source_name, CAST(:config AS jsonb)) "
                "RETURNING id"
            ),
            {
                "source_type": "git",
                "source_name": "fixture repo",
                "config": json.dumps(
                    {"url": "https://github.com/example/repo.git", "branch": "main"}
                ),
            },
        )
        return int(result.scalar_one())
