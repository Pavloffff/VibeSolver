from collections.abc import Callable, Iterator
from typing import Any, ClassVar, Protocol

from app.domain.entities import ConnectorDescriptor, RawItem


class ConnectorSPI(Protocol):
    type: ClassVar[str]
    ready: ClassVar[bool]

    def validate_config(self, config: dict[str, Any]) -> None: ...

    def fetch_snapshot(self, config: dict[str, Any]) -> Iterator[RawItem]: ...


class ConnectorCatalog(Protocol):
    def get(self, source_type: str) -> ConnectorSPI | None: ...

    def descriptors(self) -> list[ConnectorDescriptor]: ...


_default_connector_catalog_factory: Callable[[], ConnectorCatalog] | None = None


def set_default_connector_catalog(factory: Callable[[], ConnectorCatalog]) -> None:
    global _default_connector_catalog_factory
    _default_connector_catalog_factory = factory


def default_connector_catalog() -> ConnectorCatalog:
    if _default_connector_catalog_factory is None:
        raise RuntimeError("default connector catalog is not configured")
    return _default_connector_catalog_factory()
