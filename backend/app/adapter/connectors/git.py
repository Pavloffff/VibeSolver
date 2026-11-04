from collections.abc import Iterator
from typing import Any, ClassVar

from app.adapter.connectors.base import BaseConnector
from app.domain.entities import ConfigField, ConfigValidationError, RawItem


class GitConnector(BaseConnector):
    type: ClassVar[str] = "git"
    ready: ClassVar[bool] = True
    config_fields: ClassVar[list[ConfigField]] = [
        ConfigField(name="url", label="Repository URL", kind="text", required=True),
        ConfigField(
            name="branches",
            label="Branches (comma-separated)",
            kind="text",
            required=False,
        ),
        ConfigField(
            name="token_ref",
            label="Access token reference",
            kind="password",
            required=False,
        ),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        url = config.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ConfigValidationError("git source config requires a non-empty 'url'")
        branches = config.get("branches")
        if branches is not None and not _is_branch_list(branches):
            raise ConfigValidationError(
                "'branches' must be a list of branch names or a comma-separated string"
            )
        token_ref = config.get("token_ref")
        if token_ref is not None and not isinstance(token_ref, str):
            raise ConfigValidationError("'token_ref' must be a string")

    def fetch_snapshot(self, config: dict[str, Any]) -> Iterator[RawItem]:
        raise NotImplementedError


def _is_branch_list(value: object) -> bool:
    if isinstance(value, str):
        return True
    if isinstance(value, list):
        return all(isinstance(item, str) for item in value)
    return False
