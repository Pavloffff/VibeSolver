from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

IMPORT_TASK_DELAY_TARGET = "app.adapter.celery_tasks.run_source_import.delay"


class FakeAsyncResult:
    id: str = "fake-task-id"


@pytest.fixture
async def source_with_running_import(
    db_engine: AsyncEngine, git_source_id: int
) -> AsyncGenerator[int, None]:
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO imports (source_id, status, progress, error, started_at, finished_at) "
                "VALUES (:source_id, 'failed', 10, 'boom', now() - interval '1 hour', now() - interval '59 minutes')"
            ),
            {"source_id": git_source_id},
        )
        await connection.execute(
            text(
                "INSERT INTO imports (source_id, status, progress, error, started_at, finished_at) "
                "VALUES (:source_id, 'running', 42, NULL, now() - interval '1 minute', NULL)"
            ),
            {"source_id": git_source_id},
        )
    yield git_source_id


async def test_import_enqueue_returns_202_with_task_id(
    api_client: AsyncClient, git_source_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    delay_calls: dict[str, Any] = {}

    def fake_delay(*args: Any, **kwargs: Any) -> FakeAsyncResult:
        delay_calls["args"] = args
        delay_calls["kwargs"] = kwargs
        return FakeAsyncResult()

    monkeypatch.setattr(IMPORT_TASK_DELAY_TARGET, fake_delay, raising=False)
    response = await api_client.post(f"/api/v1/sources/{git_source_id}/import")
    assert response.status_code == 202
    body = response.json()
    assert isinstance(body["task_id"], str)
    assert body["task_id"] != ""
    assert git_source_id in delay_calls.get("args", ()) or git_source_id in (
        delay_calls.get("kwargs", {}).values()
    )


async def test_import_status_404_before_first_import(
    api_client: AsyncClient, git_source_id: int
) -> None:
    response = await api_client.get(f"/api/v1/sources/{git_source_id}/import")
    assert response.status_code == 404


async def test_import_status_returns_latest_import_row(
    api_client: AsyncClient, source_with_running_import: int
) -> None:
    response = await api_client.get(f"/api/v1/sources/{source_with_running_import}/import")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["progress"] == 42
    assert body["error"] is None
