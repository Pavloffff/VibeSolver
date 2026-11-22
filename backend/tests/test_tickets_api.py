from httpx import AsyncClient
from sqlalchemy import text

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

    response = await api_client.post(f"/api/v1/tickets/{ticket_id}/run")
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
    default_id = graph.json()["default_profile_id"]
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
    assert first.json()["runs"][0]["profile_name"] == "Engineer"
    assert (await api_client.get(f"{project_url}/solver-graph")).json()[
        "default_profile_id"
    ] == default_id
    assert (
        await api_client.put(profile_url, json={**settings, "name": "Review"})
    ).status_code == 200
    assert (await api_client.put(f"{profile_url}/default")).status_code == 204
    assert (await api_client.post(f"{ticket_url}/run")).status_code == 200
    assert (await api_client.delete(profile_url)).status_code == 409
    assert (
        await api_client.delete(profile_url, params={"replacement_id": default_id})
    ).status_code == 204

    history = (await api_client.get(ticket_url)).json()
    first_run, second_run = history["runs"]
    assert (first_run["profile_name"], second_run["profile_name"]) == ("Engineer", "Review")
    assert first_run["id"] != second_run["id"]
    assert all(run["finished_at"] is not None for run in history["runs"])
    assert history["steps"][0]["run_id"] is None
    for run in history["runs"]:
        steps = [step for step in history["steps"] if step["run_id"] == run["id"]]
        assert [(step["step"], step["status"]) for step in steps] == [
            ("triage", "skipped"),
            ("investigate", "completed"),
            ("resolve", "skipped"),
            ("escalate", "completed"),
        ]
