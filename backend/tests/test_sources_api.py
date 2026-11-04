from httpx import AsyncClient
from sqlalchemy import text

GIT_SOURCE_PAYLOAD: dict[str, object] = {
    "type": "git",
    "name": "main repo",
    "config": {"url": "https://github.com/x/y.git", "branch": "main"},
}

ARCHIVE_SOURCE_PAYLOAD: dict[str, object] = {
    "type": "archive",
    "name": "uploaded project",
    "config": {"upload_key": "uploads/abc123"},
}


async def test_create_git_source_returns_201(api_client: AsyncClient, clean_database: None) -> None:
    response = await api_client.post("/api/v1/sources", json=GIT_SOURCE_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["type"] == "git"
    assert body["name"] == "main repo"
    assert body["enabled"] is True
    assert body["config"] == GIT_SOURCE_PAYLOAD["config"]


async def test_created_source_appears_in_list(
    api_client: AsyncClient, clean_database: None
) -> None:
    create_response = await api_client.post("/api/v1/sources", json=GIT_SOURCE_PAYLOAD)
    created_id = create_response.json()["id"]
    list_response = await api_client.get("/api/v1/sources")
    assert list_response.status_code == 200
    items = list_response.json()
    assert [item["id"] for item in items] == [created_id]
    item = items[0]
    assert item["type"] == "git"
    assert item["name"] == "main repo"
    assert item["enabled"] is True
    assert "last_import" in item


async def test_source_without_import_has_last_import_null(
    api_client: AsyncClient, clean_database: None
) -> None:
    create_response = await api_client.post("/api/v1/sources", json=GIT_SOURCE_PAYLOAD)
    created_id = create_response.json()["id"]
    list_response = await api_client.get("/api/v1/sources")
    item = next(i for i in list_response.json() if i["id"] == created_id)
    assert item["last_import"] is None


async def test_unknown_connector_type_rejected(
    api_client: AsyncClient, clean_database: None
) -> None:
    response = await api_client.post(
        "/api/v1/sources",
        json={"type": "ftp", "name": "legacy", "config": {"url": "ftp://example.com"}},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert response.json()["detail"] != ""
    list_response = await api_client.get("/api/v1/sources")
    assert list_response.json() == []


async def test_missing_name_rejected(api_client: AsyncClient, clean_database: None) -> None:
    response = await api_client.post(
        "/api/v1/sources",
        json={"type": "git", "config": {"url": "https://github.com/x/y.git"}},
    )
    assert response.status_code == 422
    list_response = await api_client.get("/api/v1/sources")
    assert list_response.json() == []


async def test_git_source_with_empty_config_rejected(
    api_client: AsyncClient, clean_database: None
) -> None:
    response = await api_client.post(
        "/api/v1/sources",
        json={"type": "git", "name": "broken", "config": {}},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert response.json()["detail"] != ""
    list_response = await api_client.get("/api/v1/sources")
    assert list_response.json() == []


async def test_create_archive_source_returns_201(
    api_client: AsyncClient, clean_database: None
) -> None:
    response = await api_client.post("/api/v1/sources", json=ARCHIVE_SOURCE_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["type"] == "archive"
    assert body["config"] == {"upload_key": "uploads/abc123"}


async def test_project_details_include_config_and_import_state(
    api_client: AsyncClient, clean_database: None
) -> None:
    created = await api_client.post("/api/v1/sources", json=GIT_SOURCE_PAYLOAD)
    project_id = created.json()["id"]
    response = await api_client.get(f"/api/v1/sources/{project_id}")
    assert response.status_code == 200
    assert response.json()["id"] == project_id
    assert response.json()["config"] == GIT_SOURCE_PAYLOAD["config"]
    assert response.json()["last_import"] is None


async def test_project_update_merges_config_and_resources(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    async with db_engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT INTO sources (type, name, config) "
                "VALUES ('git', 'repo', CAST(:config AS jsonb)) RETURNING id"
            ),
            {"config": '{"url":"https://github.com/x/y.git","token_ref":"private"}'},
        )
        project_id = int(result.scalar_one())
    response = await api_client.patch(
        f"/api/v1/sources/{project_id}",
        json={
            "name": "renamed",
            "config": {"url": "https://github.com/x/y-fixed.git"},
            "resources": {
                "documentation": [
                    {"type": "archive", "name": "guide.zip", "config": {"upload_key": "uploads/guide"}}
                ]
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"
    assert response.json()["config"]["resources"]["documentation"][0]["name"] == "guide.zip"
    assert "token_ref" not in response.json()["config"]
    async with db_engine.begin() as connection:
        persisted = await connection.execute(
            text("SELECT config->>'token_ref' FROM sources WHERE id = :id"),
            {"id": project_id},
        )
        assert persisted.scalar_one() == "private"


async def test_project_stats_show_imported_file_count(
    api_client: AsyncClient, db_engine, clean_database: None
) -> None:
    created = await api_client.post("/api/v1/sources", json=GIT_SOURCE_PAYLOAD)
    project_id = created.json()["id"]
    response = await api_client.get(f"/api/v1/sources/{project_id}/stats")
    assert response.status_code == 200
    assert response.json() == {"file_count": 0}


async def test_archive_source_without_upload_key_rejected(
    api_client: AsyncClient, clean_database: None
) -> None:
    response = await api_client.post(
        "/api/v1/sources",
        json={"type": "archive", "name": "broken", "config": {}},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert response.json()["detail"] != ""
    list_response = await api_client.get("/api/v1/sources")
    assert list_response.json() == []


async def test_delete_source_hides_it_from_list(
    api_client: AsyncClient, clean_database: None
) -> None:
    create_response = await api_client.post("/api/v1/sources", json=GIT_SOURCE_PAYLOAD)
    created_id = create_response.json()["id"]
    delete_response = await api_client.delete(f"/api/v1/sources/{created_id}")
    assert delete_response.status_code == 204
    list_response = await api_client.get("/api/v1/sources")
    assert all(item["id"] != created_id for item in list_response.json())
