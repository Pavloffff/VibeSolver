from httpx import AsyncClient

from app.handler.schemas import sanitize_config


def test_sanitize_config_drops_token_ref() -> None:
    assert sanitize_config({"token_ref": "x", "url": "y"}) == {"url": "y"}


def test_sanitize_config_keeps_config_without_token_ref() -> None:
    assert sanitize_config({"url": "y"}) == {"url": "y"}


TOKEN_REF_PAYLOAD: dict[str, object] = {
    "type": "git",
    "name": "private repo",
    "config": {"url": "https://github.com/x/y.git", "token_ref": "vault://git/private"},
}


async def test_create_source_response_hides_token_ref(
    api_client: AsyncClient, clean_database: None
) -> None:
    response = await api_client.post("/api/v1/sources", json=TOKEN_REF_PAYLOAD)
    assert response.status_code == 201
    config = response.json()["config"]
    assert "token_ref" not in config
    assert config["url"] == "https://github.com/x/y.git"


async def test_list_sources_hides_token_ref(api_client: AsyncClient, clean_database: None) -> None:
    create_response = await api_client.post("/api/v1/sources", json=TOKEN_REF_PAYLOAD)
    assert create_response.status_code == 201
    list_response = await api_client.get("/api/v1/sources")
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1
    assert "token_ref" not in items[0]["config"]
    assert items[0]["config"]["url"] == "https://github.com/x/y.git"
