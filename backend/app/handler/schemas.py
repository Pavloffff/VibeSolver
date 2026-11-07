from typing import Any

from pydantic import BaseModel, Field

from app.domain.entities import ConfigField


class ConfigSchema(BaseModel):
    fields: list[ConfigField]


class ConnectorInfo(BaseModel):
    type: str
    ready: bool
    config_schema: ConfigSchema


class SourceCreate(BaseModel):
    type: str
    name: str
    config: dict[str, Any]


class ProjectResource(BaseModel):
    id: str | None = None
    type: str
    name: str
    config: dict[str, Any]


class SourceUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    resources: dict[str, list[ProjectResource]] | None = None


class LastImportOut(BaseModel):
    status: str
    finished_at: str | None


class SourceOut(BaseModel):
    id: int
    type: str
    name: str
    enabled: bool
    config: dict[str, Any]
    last_import: LastImportOut | None


class SourceStatsOut(BaseModel):
    file_count: int


class ResourceContentOut(BaseModel):
    content: str


class ResourceContentUpdate(BaseModel):
    content: str = Field(max_length=5_000_000)


class ImportEnqueueOut(BaseModel):
    task_id: str


class ImportStatusOut(BaseModel):
    status: str
    progress: int
    error: str | None


class UploadOut(BaseModel):
    upload_key: str


class ModelProviderCreate(BaseModel):
    provider_type: str
    name: str
    base_url: str | None = None
    api_key: str | None = None


class ModelProviderUpdate(BaseModel):
    name: str
    base_url: str | None = None
    api_key: str | None = None


class ModelProviderOut(BaseModel):
    id: int
    provider_type: str
    name: str
    base_url: str
    has_api_key: bool


class ModelProviderTypeOut(BaseModel):
    provider_type: str
    display_name: str
    default_url: str
    requires_api_key: bool
    fixed_url: bool
    sync_all_models: bool
    supports_model_pull: bool


class ProviderModelAdd(BaseModel):
    provider_model_id: str


class ModelOut(BaseModel):
    id: int
    provider_connection_id: int
    provider_type: str
    provider_name: str
    provider_model_id: str
    display_name: str
    capabilities: list[str]
    status: str
    progress: int | None
    metadata: dict[str, Any]


class ProviderAvailableModelOut(BaseModel):
    provider_model_id: str
    display_name: str
    capabilities: list[str]
    status: str
    metadata: dict[str, Any]


class ModelSelectionUpdate(BaseModel):
    model_id: int | None


class ModelSelectionOut(BaseModel):
    indexing: int | None
    documentation_generation: int | None


class OllamaPullIn(BaseModel):
    model_id: str


def sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: _sanitize_value(value) for key, value in config.items() if key != "token_ref"}


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_value(nested)
            for key, nested in value.items()
            if key != "token_ref"
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value
