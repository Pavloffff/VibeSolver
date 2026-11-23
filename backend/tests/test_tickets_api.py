from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.adapter.config import get_settings
from app.adapter.db import get_session
from app.handler.app import create_app

TICKET_PAYLOAD = {
    "title": "Не работает вход",
    "description": "При входе в админку возвращается 401",
}


async def _source_id(db_engine) -> int:
    async with db_engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO sources (type, name, config) "
                "VALUES ('git', 'tickets api repo', CAST(:config AS jsonb)) RETURNING id"
            ),
            {"config": '{"url":"https://github.com/x/y.git"}'},
        )
        return int(result.scalar_one())


async def test_create_and_list_tickets(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    source_id = await _source_id(db_engine)
    created = await api_client.post(f"/api/v1/sources/{source_id}/tickets", json=TICKET_PAYLOAD)
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "new"
    assert body["title"] == "Не работает вход"

    listed = await api_client.get(f"/api/v1/sources/{source_id}/tickets")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]

    stats = await api_client.get(f"/api/v1/sources/{source_id}/tickets/stats")
    assert stats.status_code == 200
    assert stats.json()["total"] == 1
    assert stats.json()["by_status"]["new"] == 1
    assert stats.json()["completed"] == 0


async def test_ticket_stats_empty_project(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    source_id = await _source_id(db_engine)
    response = await api_client.get(f"/api/v1/sources/{source_id}/tickets/stats")
    assert response.status_code == 200
    assert response.json() == {
        "total": 0,
        "by_status": {"new": 0, "running": 0, "answered": 0, "escalated": 0, "failed": 0},
        "completed": 0,
        "autoresolve_rate": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": None,
        "avg_cost_usd": None,
        "avg_tokens_per_ticket": 0.0,
    }


async def test_ticket_stats_unknown_project(api_client: AsyncClient, clean_database: None) -> None:
    response = await api_client.get("/api/v1/sources/999999/tickets/stats")
    assert response.status_code == 404


async def test_create_ticket_unknown_project(api_client: AsyncClient, clean_database: None) -> None:
    response = await api_client.post("/api/v1/sources/999999/tickets", json=TICKET_PAYLOAD)
    assert response.status_code == 404


async def test_create_ticket_validates_payload(
    api_client: AsyncClient, clean_database: None
) -> None:
    response = await api_client.post(
        "/api/v1/sources/1/tickets", json={"title": "a", "description": "short"}
    )
    assert response.status_code == 422


async def test_ticket_details_unknown_ticket(api_client: AsyncClient, clean_database: None) -> None:
    response = await api_client.get("/api/v1/tickets/999999")
    assert response.status_code == 404


async def test_run_ticket_without_model_returns_422(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    source_id = await _source_id(db_engine)
    created = await api_client.post(f"/api/v1/sources/{source_id}/tickets", json=TICKET_PAYLOAD)
    ticket_id = created.json()["id"]

    profile = await api_client.post(
        f"/api/v1/sources/{source_id}/solver-profiles",
        json={"name": "Engineer", "enabled": {"triage": True, "resolve": True}, "models": {}},
    )
    assert profile.status_code == 201
    response = await api_client.post(
        f"/api/v1/tickets/{ticket_id}/run", json={"profile_id": profile.json()["id"]}
    )
    assert response.status_code == 422
    assert "select a chat model" in response.json()["detail"]

    detail = await api_client.get(f"/api/v1/tickets/{ticket_id}")
    assert detail.json()["ticket"]["status"] == "new"


async def test_solver_profiles_preserve_run_boundaries_and_legacy_steps(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    source_id = await _source_id(db_engine)
    project_url = f"/api/v1/sources/{source_id}"
    graph = await api_client.get(f"{project_url}/solver-graph")
    assert graph.status_code == 200
    assert graph.json()["default_profile_id"] is None
    assert graph.json()["profiles"] == []
    assert (
        await api_client.get(f"/api/v1/models/projects/{source_id}/selections")
    ).status_code == 200
    selection = await api_client.put(
        f"/api/v1/models/projects/{source_id}/selections/ticket_resolution",
        json={"model_id": None},
    )
    assert selection.status_code == 422
    assert "Solver profile" in selection.json()["detail"]
    assert (await api_client.get(f"{project_url}/solver-graph")).json()["profiles"] == []
    settings = {"name": "Engineer", "enabled": {"triage": False, "resolve": False}, "models": {}}
    created = await api_client.post(f"{project_url}/solver-profiles", json=settings)
    assert created.status_code == 201
    profile_id = created.json()["id"]
    profile_url = f"{project_url}/solver-profiles/{profile_id}"
    ticket = await api_client.post(f"{project_url}/tickets", json=TICKET_PAYLOAD)
    ticket_id = ticket.json()["id"]
    ticket_url = f"/api/v1/tickets/{ticket_id}"
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO ticket_steps (ticket_id, step, input_json, output_json, duration_ms) "
                "VALUES (:ticket_id, 'triage', '{}', '{}', 1)"
            ),
            {"ticket_id": ticket_id},
        )

    first = await api_client.post(f"{ticket_url}/run", json={"profile_id": profile_id})
    assert first.status_code == 200
    assert first.json()["ticket"]["status"] == "escalated"
    first_result = first.json()["ticket"]["localized_result"]
    assert first_result["en"] == first.json()["ticket"]["escalate_reason"]
    assert set(first_result) == {"en", "ru", "zh"}
    assert first.json()["runs"][0]["profile_name"] == "Engineer"
    assert (await api_client.get(f"{project_url}/solver-graph")).json()[
        "default_profile_id"
    ] is None
    assert (
        await api_client.put(profile_url, json={**settings, "name": "Review"})
    ).status_code == 200
    assert (await api_client.put(f"{profile_url}/default")).status_code == 410
    assert (
        await api_client.post(
            f"{ticket_url}/run", json={"profile_id": profile_id, "comment": "Still happening"}
        )
    ).status_code == 200
    assert (await api_client.delete(profile_url)).status_code == 204
    assert (await api_client.get(f"{project_url}/solver-graph")).json()["profiles"] == []
    assert (
        await api_client.post(f"{ticket_url}/run", json={"profile_id": profile_id})
    ).status_code == 404

    history = (await api_client.get(ticket_url)).json()
    first_run, second_run = history["runs"]
    assert history["ticket"]["localized_result"] == first_result
    assert (first_run["profile_name"], second_run["profile_name"]) == ("Engineer", "Review")
    assert first_run["id"] != second_run["id"]
    assert first_run["rerun_context"] is None
    assert second_run["rerun_context"]["comment"] == "Still happening"
    assert second_run["rerun_context"]["previous_result"]["status"] == "escalated"
    assert second_run["rerun_context"]["previous_result"]["escalate_reason"]
    assert all(run["finished_at"] is not None for run in history["runs"])
    assert history["steps"][0]["run_id"] is None
    for run in history["runs"]:
        steps = [step for step in history["steps"] if step["run_id"] == run["id"]]
        assert [(step["step"], step["status"]) for step in steps] == [
            ("log_intake", "skipped"),
            ("triage", "skipped"),
            ("investigate", "completed"),
            ("resolve", "skipped"),
            ("escalate", "completed"),
        ]


async def test_diagnostic_options_are_project_and_ticket_scoped(
    api_client: AsyncClient, db_engine, clean_database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_id = await _source_id(db_engine)
    project = f"/api/v1/sources/{source_id}"
    tools_url = f"{project}/diagnostic-tools"
    tools = await api_client.get(tools_url)
    assert tools.status_code == 200
    assert tools.json()["web_provider"] is None
    assert tools.json()["allow_web_search"] is False
    assert (await api_client.put(tools_url, json={"ui_probe": "unregistered"})).status_code == 422
    ticket_id = (await api_client.post(f"{project}/tickets", json=TICKET_PAYLOAD)).json()["id"]
    options_url = f"/api/v1/tickets/{ticket_id}/diagnostic-options"
    assert (await api_client.get(options_url)).json() == {"use_web_search": False}
    assert (await api_client.put(options_url, json={"use_web_search": True})).json() == {
        "use_web_search": True
    }
    assert (await api_client.get(tools_url)).json()["allow_web_search"] is False
    assert (await api_client.put(tools_url, json={"allow_web_search": True})).status_code == 422
    monkeypatch.setitem(get_settings().diagnostic_web_providers, "public", "http://searxng")
    configured = {"web_provider": "public"}
    legacy_client = await api_client.put(tools_url, json=configured)
    assert legacy_client.json()["allow_web_search"] is False
    enabled = await api_client.put(tools_url, json={**configured, "allow_web_search": True})
    assert enabled.status_code == 200
    assert (await api_client.get(tools_url)).json()["allow_web_search"] is True
    profile = {"name": "Specialists", "enabled": {"flow": True, "logs": True}, "models": {}}
    created = await api_client.post(f"{project}/solver-profiles", json=profile)
    assert created.status_code == 201
    saved = next(
        p
        for p in (await api_client.get(f"{project}/solver-graph")).json()["profiles"]
        if p["id"] == created.json()["id"]
    )
    assert saved["enabled"]["logs"] and saved["enabled"]["flow"] and not saved["enabled"]["web"]


@pytest.mark.parametrize(
    "members",
    [
        {
            "nested/issue.txt": b"Title\nA full description",
            "nested/": b"",
            ".DS_Store": b"metadata",
        },
        {"issue.txt": b"Title\nA full description", "another.txt": b"another"},
        {"../issue.txt": b"Title\nA full description"},
        {"issue.txt": b"\xff"},
        {"issue.txt": b"x" * 100_001},
    ],
)
async def test_archive_preview(members: dict[str, bytes]) -> None:
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
        for path, value in members.items():
            output.writestr(path, value)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/tickets/archive-preview",
            content=archive.getvalue(),
            headers={"Content-Type": "application/zip"},
        )
    if "nested/issue.txt" in members:
        assert response.status_code == 200
        assert response.json() == {"text": "Title\nA full description"}
    else:
        assert response.status_code == 422


async def test_archive_preview_rejects_oversized_stream() -> None:
    async def upload() -> AsyncIterator[bytes]:
        for _ in range(3):
            yield b"x" * (512 * 1024)

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/tickets/archive-preview",
            content=upload(),
            headers={"Content-Type": "application/zip"},
        )
    assert response.status_code == 413


@pytest.mark.parametrize("payload", [None, {}, {"profile_id": None}, {"comment": "Recheck"}])
async def test_run_requires_explicit_profile(payload: dict | None) -> None:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/tickets/1/run", json=payload)
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == (["body"] if payload is None else ["body", "profile_id"])
    assert error["msg"] in {"Field required", "Input should be a valid integer"}


async def test_profile_migration_archives_only_untouched_seed(db_engine) -> None:
    migration_path = (
        Path(__file__).resolve().parents[1] / "migrations" / "00013_explicit_solver_profiles.sql"
    )
    migration = migration_path.read_text(encoding="utf-8").split("-- +goose Down")[0]
    async with db_engine.begin() as connection:
        await connection.execute(
            text("""
            CREATE TEMP TABLE solver_profiles (
                id bigint, source_id bigint, name text, triage_enabled boolean DEFAULT true,
                resolve_enabled boolean DEFAULT true, ticket_resolution bigint,
                ticket_triage bigint, ticket_resolution_cheap bigint, is_default boolean DEFAULT true,
                specialist_flags jsonb DEFAULT '{}'::jsonb
            ) ON COMMIT DROP
        """)
        )
        await connection.execute(
            text("CREATE TEMP TABLE ticket_runs (profile_id bigint) ON COMMIT DROP")
        )
        await connection.execute(
            text("""
            INSERT INTO solver_profiles (id, source_id, name, ticket_resolution)
            VALUES (1, 1, 'Default', NULL), (2, 2, 'Default', 42),
                   (3, 3, 'Engineering', NULL), (4, 4, 'Default', NULL),
                   (5, 5, 'Default', NULL), (6, 6, 'Default', NULL)
        """)
        )
        await connection.execute(text("INSERT INTO ticket_runs (profile_id) VALUES (4)"))
        await connection.execute(text("UPDATE solver_profiles SET is_default = false WHERE id = 5"))
        await connection.execute(
            text("""
            UPDATE solver_profiles SET specialist_flags = '{"web": false}'::jsonb WHERE id = 6
        """)
        )
        for statement in migration.strip().strip(";").split(";"):
            await connection.execute(text(statement))
        archived_ids = await connection.scalars(
            text("SELECT id FROM solver_profiles WHERE is_archived_seed")
        )
        assert list(archived_ids) == [1]
        assert await connection.scalar(text("SELECT count(*) FROM solver_profiles")) == 6


async def test_first_explicit_profile_can_use_archived_seed_name(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    source_id = await _source_id(db_engine)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("""
                INSERT INTO solver_profiles (source_id, name, is_default, is_archived_seed)
                VALUES (:source_id, 'Default', true, true)
            """),
            {"source_id": source_id},
        )
    project_url = f"/api/v1/sources/{source_id}"
    assert (await api_client.get(f"{project_url}/solver-graph")).json()["profiles"] == []
    created = await api_client.post(
        f"{project_url}/solver-profiles",
        json={"name": "Default", "enabled": {"triage": False, "resolve": False}, "models": {}},
    )
    assert created.status_code == 201
    assert (await api_client.get(f"{project_url}/solver-graph")).json()["profiles"] == [
        created.json()
    ]


async def test_solver_profile_rejects_embedding_only_model(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    source_id = await _source_id(db_engine)
    async with db_engine.begin() as connection:
        model_id = await connection.scalar(
            text("""
            WITH provider AS (
                INSERT INTO model_provider_connections (provider_type, name, base_url)
                VALUES ('ollama', 'test capability provider', 'http://localhost') RETURNING id
            )
            INSERT INTO workspace_models (
                provider_connection_id, provider_model_id, display_name, capabilities, status
            )
            SELECT id, 'embedding', 'Embedding only', '["embedding"]'::jsonb, 'installed'
            FROM provider RETURNING id
        """)
        )
    create = await api_client.post(
        f"/api/v1/sources/{source_id}/solver-profiles",
        json={
            "name": "Engineer",
            "enabled": {"triage": True, "resolve": True},
            "models": {"ticket_resolution": model_id},
        },
    )
    assert create.status_code == 409
    assert create.json()["detail"] == "Select an available chat model"
