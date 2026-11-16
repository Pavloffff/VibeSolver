from httpx import AsyncClient
from sqlalchemy import text


async def test_search_unknown_project_returns_404(
    api_client: AsyncClient, clean_database: None
) -> None:
    response = await api_client.post("/api/v1/sources/999999/search", json={"query": "ошибка"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


async def test_search_without_completed_indexes_returns_409(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    async with db_engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO sources (type, name, config) "
                "VALUES ('git', 'repo', CAST(:config AS jsonb)) RETURNING id"
            ),
            {"config": '{"url":"https://github.com/x/y.git"}'},
        )
        source_id = int(result.scalar_one())
    response = await api_client.post(
        f"/api/v1/sources/{source_id}/search", json={"query": "ошибка"}
    )
    assert response.status_code == 409
    assert "no completed indexes" in response.json()["detail"]


async def test_search_validates_payload(
    api_client: AsyncClient, clean_database: None
) -> None:
    response = await api_client.post("/api/v1/sources/1/search", json={"query": ""})
    assert response.status_code == 422
    response = await api_client.post(
        "/api/v1/sources/1/search", json={"query": "q", "top_k": 0}
    )
    assert response.status_code == 422
