from collections.abc import Iterator
from typing import Any, ClassVar

from app.adapter.connectors.base import BaseConnector
from app.domain.entities import ConfigField, ConfigValidationError, RawItem


class LocalFolderConnector(BaseConnector):
    type: ClassVar[str] = "local_folder"
    ready: ClassVar[bool] = True
    config_fields: ClassVar[list[ConfigField]] = [
        ConfigField(name="path", label="Folder path", kind="path", required=True),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        path = config.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ConfigValidationError("local_folder source config requires a non-empty 'path'")

    def fetch_snapshot(self, config: dict[str, Any]) -> Iterator[RawItem]:
        raise NotImplementedError
