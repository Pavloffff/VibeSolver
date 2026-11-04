from httpx import AsyncClient

from app.adapter.connectors import CONNECTOR_REGISTRY

EXPECTED_CONNECTOR_TYPES: set[str] = {"git", "local_folder", "svn", "hg"}
SKELETON_CONNECTOR_TYPES: set[str] = {"svn", "hg"}


async def test_connector_registry_lists_expected_types() -> None:
    assert EXPECTED_CONNECTOR_TYPES <= set(CONNECTOR_REGISTRY)


async def test_connectors_endpoint_returns_registry_introspection(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/connectors")
    assert response.status_code == 200
    connectors = response.json()
    assert isinstance(connectors, list)
    by_type = {entry["type"]: entry for entry in connectors}
    assert EXPECTED_CONNECTOR_TYPES <= set(by_type)
    for entry in connectors:
        assert isinstance(entry["type"], str)
        assert isinstance(entry["ready"], bool)
        fields = entry["config_schema"]["fields"]
        assert isinstance(fields, list)
        for field in fields:
            assert isinstance(field["name"], str)
            assert isinstance(field["label"], str)
            assert isinstance(field["kind"], str)
            assert isinstance(field["required"], bool)


async def test_skeleton_connectors_not_ready(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/connectors")
    assert response.status_code == 200
    by_type = {entry["type"]: entry for entry in response.json()}
    assert EXPECTED_CONNECTOR_TYPES <= set(by_type)
    for skeleton_type in SKELETON_CONNECTOR_TYPES:
        assert by_type[skeleton_type]["ready"] is False
    assert by_type["git"]["ready"] is True
    assert by_type["local_folder"]["ready"] is True
