from typing import Any

from pydantic import BaseModel

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


class ImportEnqueueOut(BaseModel):
    task_id: str


class ImportStatusOut(BaseModel):
    status: str
    progress: int
    error: str | None


class UploadOut(BaseModel):
    upload_key: str


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
