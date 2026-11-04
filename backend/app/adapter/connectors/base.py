from collections.abc import Iterator
from typing import Any, ClassVar

from app.domain.entities import ConfigField, RawItem


class BaseConnector:
    type: ClassVar[str] = ""
    ready: ClassVar[bool] = False
    config_fields: ClassVar[list[ConfigField]] = []

    def validate_config(self, config: dict[str, Any]) -> None:
        raise NotImplementedError

    def fetch_snapshot(self, config: dict[str, Any]) -> Iterator[RawItem]:
        raise NotImplementedError
