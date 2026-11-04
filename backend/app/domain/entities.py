from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ConfigValidationError(ValueError):
    pass


class UnknownConnectorError(ValueError):
    def __init__(self, source_type: str) -> None:
        super().__init__(f"unknown source type: {source_type}")
        self.source_type = source_type


class UnknownStorageStrategyError(ValueError):
    def __init__(self, strategy_key: str) -> None:
        super().__init__(f"unknown storage strategy: {strategy_key}")
        self.strategy_key = strategy_key


class SourceNotFoundError(LookupError):
    pass


class ImportNotFoundError(LookupError):
    pass


class QueueUnavailableError(RuntimeError):
    pass


class ConfigField(BaseModel):
    name: str
    label: str
    kind: Literal["text", "path", "password"]
    required: bool


@dataclass(slots=True)
class RawItem:
    path: str
    content: bytes
    meta: dict[str, Any]


@dataclass(slots=True)
class ImportSnapshot:
    status: str
    progress: int
    error: str | None
    finished_at: datetime | None


@dataclass(slots=True)
class ConnectorDescriptor:
    type: str
    ready: bool
    config_fields: list[ConfigField]
