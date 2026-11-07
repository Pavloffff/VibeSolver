from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.model_provider_entities import (
    ProviderConnection,
    ProviderCredentials,
    ProviderModel,
    WorkspaceModelEntry,
)
from app.domain.models import ModelProviderConnection, ProjectModelAssignment, WorkspaceModel


class ModelProviderSqlRepository:
    def __init__(self, session: AsyncSession, secrets_key: str | None) -> None:
        self._session = session
        self._secrets_key = secrets_key

    async def list_connections(self) -> list[ProviderConnection]:
        result = await self._session.scalars(
            select(ModelProviderConnection).order_by(ModelProviderConnection.id)
        )
        return [_to_connection(item) for item in result.all()]

    async def get_connection(self, connection_id: int) -> ProviderConnection | None:
        item = await self._session.get(ModelProviderConnection, connection_id)
        return _to_connection(item) if item is not None else None

    async def get_credentials(self, connection_id: int) -> ProviderCredentials | None:
        item = await self._session.get(ModelProviderConnection, connection_id)
        if item is None:
            return None
        api_key: str | None = None
        if item.credential_ciphertext is not None:
            if not self._secrets_key:
                raise RuntimeError("model secret encryption key is not configured")
            result = await self._session.execute(
                select(func.pgp_sym_decrypt(item.credential_ciphertext, self._secrets_key))
            )
            api_key = result.scalar_one()
        return ProviderCredentials(
            id=item.id,
            provider_type=item.provider_type,
            name=item.name,
            base_url=item.base_url,
            api_key=api_key,
        )

    async def create_connection(
        self, provider_type: str, name: str, base_url: str, api_key: str | None
    ) -> ProviderConnection:
        if api_key and not self._secrets_key:
            raise RuntimeError("VIBESOLVER_MODEL_SECRETS_KEY must be configured to save API keys")
        encrypted = func.pgp_sym_encrypt(api_key, self._secrets_key) if api_key else None
        item = ModelProviderConnection(
            provider_type=provider_type,
            name=name,
            base_url=base_url,
            credential_ciphertext=encrypted,
        )
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return _to_connection(item)

    async def update_connection(
        self, connection_id: int, name: str, base_url: str, api_key: str | None
    ) -> ProviderConnection | None:
        item = await self._session.get(ModelProviderConnection, connection_id)
        if item is None:
            return None
        if api_key:
            if not self._secrets_key:
                raise RuntimeError(
                    "VIBESOLVER_MODEL_SECRETS_KEY must be configured to save API keys"
                )
            item.credential_ciphertext = func.pgp_sym_encrypt(api_key, self._secrets_key)
        item.name = name
        item.base_url = base_url
        await self._session.commit()
        await self._session.refresh(item)
        return _to_connection(item)

    async def delete_connection(self, connection_id: int) -> bool:
        item = await self._session.get(ModelProviderConnection, connection_id)
        if item is None:
            return False
        await self._session.delete(item)
        await self._session.commit()
        return True

    async def list_models(self, connection_id: int | None = None) -> list[WorkspaceModelEntry]:
        query = select(WorkspaceModel, ModelProviderConnection).join(
            ModelProviderConnection,
            WorkspaceModel.provider_connection_id == ModelProviderConnection.id,
        )
        if connection_id is not None:
            query = query.where(WorkspaceModel.provider_connection_id == connection_id)
        result = await self._session.execute(query.order_by(WorkspaceModel.id))
        return [_to_model(model, connection) for model, connection in result.all()]

    async def get_model(self, model_id: int) -> WorkspaceModelEntry | None:
        result = await self._session.execute(
            select(WorkspaceModel, ModelProviderConnection)
            .join(ModelProviderConnection)
            .where(WorkspaceModel.id == model_id)
        )
        row = result.one_or_none()
        return _to_model(*row) if row is not None else None

    async def upsert_models(
        self, connection_id: int, models: list[ProviderModel]
    ) -> list[WorkspaceModelEntry]:
        connection = await self._session.get(ModelProviderConnection, connection_id)
        if connection is None:
            return []
        for model in models:
            item = await self._session.scalar(
                select(WorkspaceModel).where(
                    WorkspaceModel.provider_connection_id == connection_id,
                    WorkspaceModel.provider_model_id == model.provider_model_id,
                )
            )
            if item is None:
                item = WorkspaceModel(
                    provider_connection_id=connection_id,
                    provider_model_id=model.provider_model_id,
                    display_name=model.display_name,
                    capabilities=model.capabilities,
                    status=model.status,
                    progress=model.progress,
                    metadata_json=model.metadata,
                )
                self._session.add(item)
            else:
                item.display_name = model.display_name
                item.capabilities = model.capabilities
                item.status = model.status
                item.progress = model.progress
                item.metadata_json = model.metadata
        await self._session.commit()
        result = await self._session.execute(
            select(WorkspaceModel, ModelProviderConnection)
            .join(ModelProviderConnection)
            .where(WorkspaceModel.provider_connection_id == connection_id)
            .order_by(WorkspaceModel.id)
        )
        return [_to_model(model, provider) for model, provider in result.all()]

    async def add_model(self, connection_id: int, model: ProviderModel) -> WorkspaceModelEntry:
        await self.upsert_models(connection_id, [model])
        result = await self._session.execute(
            select(WorkspaceModel, ModelProviderConnection)
            .join(ModelProviderConnection)
            .where(
                WorkspaceModel.provider_connection_id == connection_id,
                WorkspaceModel.provider_model_id == model.provider_model_id,
            )
        )
        return _to_model(*result.one())

    async def update_model(
        self, connection_id: int, model: ProviderModel
    ) -> WorkspaceModelEntry | None:
        item = await self._session.scalar(
            select(WorkspaceModel).where(
                WorkspaceModel.provider_connection_id == connection_id,
                WorkspaceModel.provider_model_id == model.provider_model_id,
            )
        )
        if item is None:
            return None
        item.display_name = model.display_name
        item.capabilities = model.capabilities
        item.status = model.status
        item.progress = model.progress
        item.metadata_json = model.metadata
        await self._session.commit()
        return await self.get_model(item.id)

    async def delete_model(self, model_id: int) -> bool:
        item = await self._session.get(WorkspaceModel, model_id)
        if item is None:
            return False
        await self._session.delete(item)
        await self._session.commit()
        return True

    async def get_project_selections(self, source_id: int) -> dict[str, int]:
        result = await self._session.execute(
            select(ProjectModelAssignment.role, ProjectModelAssignment.model_id).where(
                ProjectModelAssignment.source_id == source_id
            )
        )
        return {role: model_id for role, model_id in result.all()}

    async def set_project_selection(self, source_id: int, role: str, model_id: int | None) -> None:
        item = await self._session.get(ProjectModelAssignment, (source_id, role))
        if model_id is None:
            if item is not None:
                await self._session.delete(item)
        elif item is None:
            self._session.add(
                ProjectModelAssignment(source_id=source_id, role=role, model_id=model_id)
            )
        else:
            item.model_id = model_id
        await self._session.commit()


def _to_connection(item: ModelProviderConnection) -> ProviderConnection:
    return ProviderConnection(
        id=item.id,
        provider_type=item.provider_type,
        name=item.name,
        base_url=item.base_url,
        has_api_key=item.credential_ciphertext is not None,
    )


def _to_model(item: WorkspaceModel, connection: ModelProviderConnection) -> WorkspaceModelEntry:
    return WorkspaceModelEntry(
        id=item.id,
        provider_connection_id=connection.id,
        provider_type=connection.provider_type,
        provider_name=connection.name,
        provider_model_id=item.provider_model_id,
        display_name=item.display_name,
        capabilities=list(item.capabilities),
        status=item.status,
        progress=item.progress,
        metadata=dict(item.metadata_json),
    )
