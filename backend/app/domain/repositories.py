from collections.abc import Iterator
from typing import Any, ClassVar, Protocol

from app.domain.entities import ConnectorDescriptor, ImportSnapshot, RawItem
from app.domain.models import Import, Source


class ConnectorSPI(Protocol):
    type: ClassVar[str]
    ready: ClassVar[bool]

    def validate_config(self, config: dict[str, Any]) -> None: ...

    def fetch_snapshot(self, config: dict[str, Any]) -> Iterator[RawItem]: ...


class ConnectorCatalog(Protocol):
    def get(self, source_type: str) -> ConnectorSPI | None: ...

    def descriptors(self) -> list[ConnectorDescriptor]: ...


class SourceRepository(Protocol):
    async def add(self, source_type: str, name: str, config: dict[str, Any]) -> Source: ...

    async def get_any(self, source_id: int) -> Source | None: ...

    async def get_enabled(self, source_id: int) -> Source | None: ...

    async def set_enabled(self, source_id: int, enabled: bool) -> None: ...

    async def list_enabled_with_last_import(self) -> list[tuple[Source, ImportSnapshot | None]]: ...


class ImportRepository(Protocol):
    async def latest_for_source(self, source_id: int) -> Import | None: ...


class ImportEnqueuer(Protocol):
    def __call__(self, source_id: int) -> str: ...
