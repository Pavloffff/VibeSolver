from collections.abc import Iterator
from typing import Any, ClassVar

from app.adapter.connectors.base import BaseConnector
from app.domain.entities import ConfigField, ConfigValidationError, RawItem


class SvnConnector(BaseConnector):
    type: ClassVar[str] = "svn"
    ready: ClassVar[bool] = False
    config_fields: ClassVar[list[ConfigField]] = [
        ConfigField(name="url", label="Repository URL", kind="text", required=True),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        url = config.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ConfigValidationError("svn source config requires a non-empty 'url'")

    def fetch_snapshot(
        self, config: dict[str, Any], work_dir: str | None = None
    ) -> Iterator[RawItem]:
        raise NotImplementedError
