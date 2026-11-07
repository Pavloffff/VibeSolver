from typing import Protocol

from app.domain.model_provider_entities import (
    ProviderConnection,
    ProviderCredentials,
    ProviderModel,
    WorkspaceModelEntry,
)


class ModelProviderRepository(Protocol):
    async def list_connections(self) -> list[ProviderConnection]: ...

    async def get_connection(self, connection_id: int) -> ProviderConnection | None: ...

    async def get_credentials(self, connection_id: int) -> ProviderCredentials | None: ...

    async def create_connection(
        self, provider_type: str, name: str, base_url: str, api_key: str | None
    ) -> ProviderConnection: ...

    async def update_connection(
        self, connection_id: int, name: str, base_url: str, api_key: str | None
    ) -> ProviderConnection | None: ...

    async def delete_connection(self, connection_id: int) -> bool: ...

    async def list_models(self, connection_id: int | None = None) -> list[WorkspaceModelEntry]: ...

    async def get_model(self, model_id: int) -> WorkspaceModelEntry | None: ...

    async def upsert_models(
        self, connection_id: int, models: list[ProviderModel]
    ) -> list[WorkspaceModelEntry]: ...

    async def add_model(self, connection_id: int, model: ProviderModel) -> WorkspaceModelEntry: ...

    async def update_model(
        self, connection_id: int, model: ProviderModel
    ) -> WorkspaceModelEntry | None: ...

    async def delete_model(self, model_id: int) -> bool: ...

    async def get_project_selections(self, source_id: int) -> dict[str, int]: ...

    async def set_project_selection(
        self, source_id: int, role: str, model_id: int | None
    ) -> None: ...
