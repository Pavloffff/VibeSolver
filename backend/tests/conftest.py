"""Test infrastructure for VibeSolver backend API tests.

Database strategy: tests run against a real Postgres instance discovered at
session start. Resolution order:
1. VIBESOLVER_DATABASE_URL environment variable (host, port, db, credentials).
2. postgresql://vibesolver:vibesolver@localhost:5433/vibesolver
3. postgresql://vibesolver:vibesolver@localhost:5432/vibesolver

If none of the candidates is reachable, all database-backed tests are skipped
with the reason "postgres not reachable". Schema (sources, imports,
imported_files) must be applied via goose migrations beforehand.
Each test starts from empty tables: the clean_database fixture truncates
sources CASCADE, which cascades to imports and imported_files.
"""

import asyncio
import json
import os
import sys
from collections.abc import AsyncGenerator

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.handler.app import create_app

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

FALLBACK_TEST_DATABASE_DSNS: tuple[str, ...] = (
    "postgresql://vibesolver:vibesolver@localhost:5433/vibesolver",
    "postgresql://vibesolver:vibesolver@localhost:5432/vibesolver",
)

API_BASE_URL = "http://test"


def is_dsn_reachable(dsn: str) -> bool:
    try:
        with psycopg.connect(dsn, connect_timeout=2):
            return True
    except psycopg.Error:
        return False


@pytest.fixture(scope="session")
def test_database_dsn() -> str:
    candidates: list[str] = []
    env_dsn = os.environ.get("VIBESOLVER_DATABASE_URL")
    if env_dsn:
        candidates.append(env_dsn)
    candidates.extend(FALLBACK_TEST_DATABASE_DSNS)
    for dsn in candidates:
        if is_dsn_reachable(dsn):
            return dsn
    pytest.skip("postgres not reachable")


def to_async_dsn(dsn: str) -> str:
    return dsn.replace("postgresql://", "postgresql+psycopg_async://", 1)


@pytest.fixture
async def db_engine(test_database_dsn: str) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(to_async_dsn(test_database_dsn), poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_database(db_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    async with db_engine.begin() as connection:
        await connection.execute(text("TRUNCATE TABLE sources CASCADE"))


@pytest.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
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
