from collections.abc import Iterator
from typing import Any, ClassVar

from app.adapter.connectors.base import BaseConnector
from app.domain.entities import ConfigField, ConfigValidationError, RawItem


class MercurialConnector(BaseConnector):
    type: ClassVar[str] = "hg"
    ready: ClassVar[bool] = False
    config_fields: ClassVar[list[ConfigField]] = [
        ConfigField(name="url", label="Repository URL", kind="text", required=True),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        url = config.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ConfigValidationError("hg source config requires a non-empty 'url'")

    def fetch_snapshot(self, config: dict[str, Any]) -> Iterator[RawItem]:
        raise NotImplementedError
