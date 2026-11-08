import asyncio
import ipaddress
import json
from collections.abc import AsyncIterator, Iterator, Mapping
from urllib.parse import urlsplit

from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import (
    ModelProviderDefinition,
    ProviderConnection,
    ProviderCredentials,
    ProviderModel,
    ProviderUnavailableError,
    WorkspaceModelEntry,
)
from app.domain.repositories import ModelProviderRepository, SourceRepository

PROJECT_MODEL_ROLES = {
    "indexing": "embedding",
    "documentation_generation": "chat",
}


class ModelProviderNotFoundError(LookupError):
    pass


class ModelProviderValidationError(ValueError):
    pass


class ModelProviderUsecase:
    def __init__(
        self,
        models: ModelProviderRepository,
        sources: SourceRepository,
        providers: Mapping[str, ModelProviderDefinition],
        request_timeout: int,
    ) -> None:
        self._models = models
        self._sources = sources
        self._providers = providers
        self._request_timeout = request_timeout

    async def list_connections(self) -> list[ProviderConnection]:
        return await self._models.list_connections()

    async def list_models(self, connection_id: int | None = None) -> list[WorkspaceModelEntry]:
        return await self._models.list_models(connection_id)

    async def test_connection(
        self, provider_type: str, name: str, base_url: str | None, api_key: str | None
    ) -> int:
        connection, definition = self._candidate(provider_type, name, base_url, api_key)
        available = await asyncio.to_thread(
            definition.adapter.list_models, connection, self._request_timeout
        )
        return len(available)

    async def test_saved_connection(self, connection_id: int) -> int:
        connection = await self._credentials(connection_id)
        definition = self._definition(connection.provider_type)
        models = await asyncio.to_thread(
            definition.adapter.list_models, connection, self._request_timeout
        )
        return len(models)

    async def create_connection(
        self, provider_type: str, name: str, base_url: str | None, api_key: str | None
    ) -> ProviderConnection:
        connection, definition = self._candidate(provider_type, name, base_url, api_key)
        available_models = await asyncio.to_thread(
            definition.adapter.list_models, connection, self._request_timeout
        )
        saved_connection = await self._models.create_connection(
            connection.provider_type, connection.name, connection.base_url, connection.api_key
        )
        if definition.sync_all_models:
            await self._models.upsert_models(saved_connection.id, available_models)
        return saved_connection

    async def update_connection(
        self,
        connection_id: int,
        name: str,
        base_url: str | None,
        api_key: str | None,
    ) -> ProviderConnection:
        stored = await self._credentials(connection_id)
        connection, definition = self._candidate(
            stored.provider_type,
            name,
            base_url or stored.base_url,
            api_key if api_key else stored.api_key,
            connection_id,
        )
        available_models = await asyncio.to_thread(
            definition.adapter.list_models, connection, self._request_timeout
        )
        updated = await self._models.update_connection(
            connection_id, connection.name, connection.base_url, api_key
        )
        if updated is None:
            raise ModelProviderNotFoundError(str(connection_id))
        if definition.sync_all_models:
            await self._models.upsert_models(updated.id, available_models)
        return updated

    async def delete_connection(self, connection_id: int) -> None:
        if not await self._models.delete_connection(connection_id):
            raise ModelProviderNotFoundError(str(connection_id))

    async def available_models(self, connection_id: int) -> list[ProviderModel]:
        connection = await self._credentials(connection_id)
        definition = self._definition(connection.provider_type)
        return await asyncio.to_thread(
            definition.adapter.list_models, connection, self._request_timeout
        )

    async def sync_models(self, connection_id: int) -> list[WorkspaceModelEntry]:
        connection = await self._credentials(connection_id)
        definition = self._definition(connection.provider_type)
        if not definition.sync_all_models:
            raise ModelProviderValidationError(
                "Select specific models from this provider's catalog"
            )
        models = await asyncio.to_thread(
            definition.adapter.list_models, connection, self._request_timeout
        )
        return await self._models.upsert_models(connection_id, models)

    async def add_model(self, connection_id: int, provider_model_id: str) -> WorkspaceModelEntry:
        model_id = provider_model_id.strip()
        if not model_id:
            raise ModelProviderValidationError("model ID must not be empty")
        available = await self.available_models(connection_id)
        candidate = next(
            (model for model in available if model.provider_model_id == model_id), None
        )
        if candidate is None:
            raise ModelProviderValidationError("model is not available from this provider")
        return await self._models.add_model(connection_id, candidate)

    async def delete_model(self, model_id: int) -> None:
        if not await self._models.delete_model(model_id):
            raise ModelProviderNotFoundError(str(model_id))

    async def project_selections(self, source_id: int) -> dict[str, int]:
        await self._require_source(source_id)
        return await self._models.get_project_selections(source_id)

    async def set_project_selection(
        self, source_id: int, role: str, model_id: int | None
    ) -> dict[str, int]:
        expected_capability = PROJECT_MODEL_ROLES.get(role)
        if expected_capability is None:
            raise ModelProviderValidationError("unsupported project model role")
        await self._require_source(source_id)
        if model_id is not None:
            model = await self._models.get_model(model_id)
            if model is None or expected_capability not in model.capabilities:
                raise ModelProviderValidationError(
                    f"selected model does not support {expected_capability}"
                )
            if role == "indexing" and model.provider_type == "openrouter":
                raise ModelProviderValidationError(
                    "Indexing source code and project files requires a local embedding provider"
                )
            if model.status not in {"available", "installed"}:
                raise ModelProviderValidationError("selected model is not ready")
        await self._models.set_project_selection(source_id, role, model_id)
        return await self._models.get_project_selections(source_id)

    async def pull_ollama_model(self, connection_id: int, model_id: str) -> AsyncIterator[bytes]:
        model_id = model_id.strip()
        if not model_id:
            yield _ndjson({"error": "model tag must not be empty"})
            return
        connection = await self._credentials(connection_id)
        definition = self._definition(connection.provider_type)
        if not definition.supports_model_pull:
            yield _ndjson({"error": "this provider does not support downloading model weights"})
            return
        entry = ProviderModel(
            provider_model_id=model_id,
            display_name=model_id,
            capabilities=[],
            status="pulling",
            progress=0,
        )
        await self._models.add_model(connection_id, entry)
        yield _ndjson({"status": "starting", "progress": 0, "model_id": model_id})
        iterator = definition.adapter.pull_model(connection, model_id, self._request_timeout)
        completed = False
        try:
            while True:
                value = await asyncio.to_thread(_next_or_none, iterator)
                if value is None:
                    break
                status = value.get("status")
                total = value.get("total")
                amount = value.get("completed")
                progress = (
                    min(99, int(amount * 100 / total))
                    if isinstance(amount, int) and isinstance(total, int) and total > 0
                    else None
                )
                if isinstance(status, str) and status.lower() in {"success", "complete"}:
                    completed = True
                    break
                if value.get("error"):
                    raise ProviderUnavailableError(str(value["error"])[:300])
                metadata = {"pull_status": status} if isinstance(status, str) else {}
                await self._models.upsert_models(
                    connection_id,
                    [ProviderModel(model_id, model_id, [], "pulling", progress, metadata)],
                )
                yield _ndjson({"status": status, "progress": progress, "model_id": model_id})
            if not completed:
                raise ProviderUnavailableError("Ollama closed the pull stream before completion")
            refreshed = await asyncio.to_thread(
                definition.adapter.list_models, connection, self._request_timeout
            )
            model = next((item for item in refreshed if item.provider_model_id == model_id), None)
            if model is None:
                raise ProviderUnavailableError(
                    "Ollama completed the pull but the model is not listed"
                )
            await self._models.upsert_models(connection_id, [model])
            yield _ndjson({"status": "success", "progress": 100, "model_id": model_id})
        except asyncio.CancelledError:
            await asyncio.to_thread(_close_iterator, iterator)
            await self._models.upsert_models(
                connection_id,
                [ProviderModel(model_id, model_id, [], "cancelled", None, {})],
            )
            raise
        except ProviderUnavailableError as exc:
            await self._models.upsert_models(
                connection_id,
                [ProviderModel(model_id, model_id, [], "error", None, {"error": str(exc)})],
            )
            yield _ndjson({"status": "error", "error": str(exc), "model_id": model_id})
        finally:
            await asyncio.to_thread(_close_iterator, iterator)

    async def _require_source(self, source_id: int) -> None:
        if await self._sources.get_any(source_id) is None:
            raise SourceNotFoundError(f"project not found: {source_id}")

    async def _credentials(self, connection_id: int) -> ProviderCredentials:
        result = await self._models.get_credentials(connection_id)
        if result is None:
            raise ModelProviderNotFoundError(str(connection_id))
        return result

    def _definition(self, provider_type: str) -> ModelProviderDefinition:
        definition = self._providers.get(provider_type)
        if definition is None:
            raise ModelProviderValidationError("unsupported model provider")
        return definition

    def _candidate(
        self,
        provider_type: str,
        name: str,
        base_url: str | None,
        api_key: str | None,
        connection_id: int = 0,
    ) -> tuple[ProviderCredentials, ModelProviderDefinition]:
        definition = self._definition(provider_type)
        normalized_name = name.strip()
        if not normalized_name:
            raise ModelProviderValidationError("connection name must not be empty")
        if definition.requires_api_key and not api_key:
            raise ModelProviderValidationError("API key is required for this provider")
        normalized_url = normalize_provider_url(
            provider_type, base_url or definition.default_url, definition
        )
        return (
            ProviderCredentials(
                id=connection_id,
                provider_type=provider_type,
                name=normalized_name,
                base_url=normalized_url,
                api_key=api_key or None,
            ),
            definition,
        )


def normalize_provider_url(
    provider_type: str, url: str, definition: ModelProviderDefinition
) -> str:
    candidate = url.strip().rstrip("/")
    if definition.fixed_url:
        if candidate != definition.default_url:
            raise ModelProviderValidationError("provider URL is fixed")
        return candidate
    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ModelProviderValidationError(
            "provider URL must be an HTTP(S) address without credentials"
        )
    hostname = parsed.hostname.lower()
    if hostname not in {"localhost", "host.docker.internal"}:
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError as exc:
            raise ModelProviderValidationError(
                "local provider URL must use localhost, host.docker.internal or a private IP address"
            ) from exc
        if not (address.is_private or address.is_loopback) or address.is_link_local:
            raise ModelProviderValidationError(
                "local provider URL must use a private network address"
            )
    if provider_type == "freetoken" and not parsed.path.rstrip("/").endswith("/v1"):
        candidate = f"{candidate}/v1"
    if provider_type == "ollama" and parsed.path.rstrip("/") == "/api":
        candidate = candidate[: -len("/api")]
    return candidate


def _next_or_none(iterator: Iterator[dict[str, object]]) -> dict[str, object] | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def _close_iterator(iterator: Iterator[dict[str, object]]) -> None:
    close = getattr(iterator, "close", None)
    if callable(close):
        close()


def _ndjson(value: dict[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8")
