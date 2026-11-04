from collections.abc import Iterator
from typing import Any

import pytest

from app.adapter.connectors import CONNECTOR_REGISTRY
from app.adapter.connectors.base import BaseConnector
from app.adapter.connectors.hg import MercurialConnector
from app.adapter.connectors.svn import SvnConnector
from app.domain.entities import ConfigValidationError

SKELETON_CLASSES: list[type[BaseConnector]] = [SvnConnector, MercurialConnector]


@pytest.mark.parametrize("connector_class", SKELETON_CLASSES)
def test_skeleton_validate_config_ok(connector_class: type[BaseConnector]) -> None:
    connector_class().validate_config({"url": "https://example.com/repo"})


@pytest.mark.parametrize("connector_class", SKELETON_CLASSES)
def test_skeleton_validate_config_rejects_empty(
    connector_class: type[BaseConnector],
) -> None:
    with pytest.raises(ConfigValidationError):
        connector_class().validate_config({})


@pytest.mark.parametrize("connector_class", SKELETON_CLASSES)
def test_skeleton_fetch_snapshot_not_implemented(
    connector_class: type[BaseConnector],
) -> None:
    connector = connector_class()
    config: dict[str, Any] = {"url": "https://example.com/repo"}
    with pytest.raises(NotImplementedError):
        stream: Iterator[Any] = connector.fetch_snapshot(config)
        list(stream)


@pytest.mark.parametrize(
    ("connector_class", "type_key"),
    [(SvnConnector, "svn"), (MercurialConnector, "hg")],
)
def test_skeleton_registered_not_ready(
    connector_class: type[BaseConnector],
    type_key: str,
) -> None:
    assert CONNECTOR_REGISTRY[type_key] is connector_class
    assert CONNECTOR_REGISTRY[type_key].ready is False
