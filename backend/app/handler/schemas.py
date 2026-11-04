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


class ImportEnqueueOut(BaseModel):
    task_id: str


class ImportStatusOut(BaseModel):
    status: str
    progress: int
    error: str | None


def sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key != "token_ref"}
