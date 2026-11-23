import json
from collections.abc import AsyncGenerator, Iterator
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapter.repositories import ModelProviderSqlRepository, SourceSqlRepository
from app.domain.model_provider_entities import (
    ModelProviderDefinition,
    ProviderConnection,
    ProviderCredentials,
    ProviderModel,
)
from app.domain.solver import SolverModels
from app.usecase.model_providers import PROJECT_MODEL_ROLES, ModelProviderUsecase

SECRETS_KEY = "test-secrets-key"
ZAI_URL = "https://api.z.ai/api/paas/v4"


def test_project_model_roles_exclude_solver_assignments() -> None:
    assert PROJECT_MODEL_ROLES.keys().isdisjoint(SolverModels.model_fields)


@pytest.fixture
async def clean_model_providers(db_engine: Any) -> AsyncGenerator[None, None]:
    async with db_engine.begin() as connection:
        await connection.execute(text("TRUNCATE TABLE model_provider_connections CASCADE"))
    yield


@pytest.fixture
async def db_session(db_engine: Any) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


async def test_catalog_lists_zai_as_default_provider(api_client: Any) -> None:
    response = await api_client.get("/api/v1/models/providers/catalog")
    assert response.status_code == 200
    catalog = response.json()
    assert [item["provider_type"] for item in catalog] == [
        "zai",
        "kimi",
        "anthropic",
        "openai",
        "freetoken",
        "ollama",
        "openrouter",
    ]
    zai = catalog[0]
    assert zai["display_name"] == "Z.ai"
    assert zai["default_url"] == ZAI_URL
    assert zai["requires_api_key"] is True
    assert zai["fixed_url"] is True
    assert zai["sync_all_models"] is False


async def test_api_key_is_stored_encrypted_and_returned_only_via_credentials(
    db_engine: Any, db_session: AsyncSession, clean_model_providers: None
) -> None:
    repository = ModelProviderSqlRepository(db_session, SECRETS_KEY)
    connection = await repository.create_connection("zai", "Z.ai", ZAI_URL, "secret-api-key")
    assert connection.has_api_key is True

    async with db_engine.begin() as database:
        raw = await database.execute(
            text(
                "SELECT credential_ciphertext FROM model_provider_connections "
                "WHERE id = :connection_id"
            ),
            {"connection_id": connection.id},
        )
        ciphertext = raw.scalar_one()
    assert b"secret-api-key" not in ciphertext

    credentials = await repository.get_credentials(connection.id)
    assert credentials is not None
    assert credentials.api_key == "secret-api-key"

    listed = await repository.list_connections()
    assert listed[0].has_api_key is True


async def test_update_without_api_key_preserves_stored_secret(
    db_session: AsyncSession, clean_model_providers: None
) -> None:
    repository = ModelProviderSqlRepository(db_session, SECRETS_KEY)
    connection = await repository.create_connection("zai", "Z.ai", ZAI_URL, "secret-api-key")
    updated = await repository.update_connection(connection.id, "Z.ai prod", ZAI_URL, None)
    assert updated is not None
    credentials = await repository.get_credentials(connection.id)
    assert credentials is not None
    assert credentials.api_key == "secret-api-key"
    assert credentials.name == "Z.ai prod"


class FakePullAdapter:
    def __init__(self) -> None:
        self.pulled: list[str] = []

    def list_models(self, connection: ProviderCredentials, timeout: int) -> list[ProviderModel]:
        return [
            ProviderModel(
                provider_model_id="llama3",
                display_name="llama3",
                capabilities=["chat"],
                status="installed",
            )
        ]

    def pull_model(
        self, connection: ProviderCredentials, model_id: str, timeout: int
    ) -> Iterator[dict[str, Any]]:
        self.pulled.append(model_id)
        yield {"status": "pulling manifest"}
        yield {"status": "downloading", "completed": 40, "total": 100}
        yield {"status": "success"}


async def test_ollama_pull_streams_progress_and_finishes_installed(
    db_session: AsyncSession, clean_model_providers: None
) -> None:
    adapter = FakePullAdapter()
    models = ModelProviderSqlRepository(db_session, None)
    await models.create_connection("ollama", "Ollama", "http://localhost:11434", None)
    usecase = ModelProviderUsecase(
        models=models,
        sources=SourceSqlRepository(db_session),
        providers={
            "ollama": ModelProviderDefinition(
                adapter=adapter,
                default_url="http://localhost:11434",
                display_name="Ollama",
                requires_api_key=False,
                supports_model_pull=True,
            )
        },
        request_timeout=5,
    )
    connection = (await models.list_connections())[0]

    chunks = [chunk async for chunk in usecase.pull_ollama_model(connection.id, "llama3")]
    events = [json.loads(chunk) for chunk in chunks]

    assert adapter.pulled == ["llama3"]
    assert [event["status"] for event in events] == [
        "starting",
        "pulling manifest",
        "downloading",
        "success",
    ]
    assert events[-1]["progress"] == 100
    assert events[2]["progress"] == 40

    workspace = await models.list_models(connection.id)
    assert len(workspace) == 1
    assert workspace[0].provider_model_id == "llama3"
    assert workspace[0].status == "installed"
    assert workspace[0].capabilities == ["chat"]


async def test_connection_update_does_not_contact_provider_or_clear_key() -> None:
    adapter = Mock()
    adapter.list_models.side_effect = AssertionError("Updates must not contact the provider")
    repository = Mock()
    repository.get_credentials = AsyncMock(
        return_value=ProviderCredentials(41, "zai", "Before", ZAI_URL, "old-secret")
    )
    repository.update_connection = AsyncMock(
        return_value=ProviderConnection(41, "zai", "After", ZAI_URL, True)
    )
    usecase = ModelProviderUsecase(
        repository,
        Mock(),
        {"zai": ModelProviderDefinition(adapter, ZAI_URL, "Z.ai", True, fixed_url=True)},
        request_timeout=5,
    )

    updated = await usecase.update_connection(41, "  After  ", None, "")

    assert updated.name == "After"
    assert updated.has_api_key
    repository.update_connection.assert_awaited_once_with(41, "After", ZAI_URL, None)
    adapter.list_models.assert_not_called()
    repository.upsert_models.assert_not_called()
