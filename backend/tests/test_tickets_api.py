from httpx import AsyncClient
from sqlalchemy import text

TICKET_PAYLOAD = {"title": "Не работает вход", "description": "При входе в админку возвращается 401"}


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


async def test_create_ticket_unknown_project(api_client: AsyncClient, clean_database: None) -> None:
    response = await api_client.post("/api/v1/sources/999999/tickets", json=TICKET_PAYLOAD)
    assert response.status_code == 404


async def test_create_ticket_validates_payload(
    api_client: AsyncClient, clean_database: None
) -> None:
    response = await api_client.post("/api/v1/sources/1/tickets", json={"title": "a", "description": "short"})
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
