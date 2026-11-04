from typing import Any

from app.domain.entities import (
    ConfigValidationError,
    ImportNotFoundError,
    ImportSnapshot,
    SourceNotFoundError,
    UnknownConnectorError,
)
from app.domain.models import Source
from app.domain.repositories import (
    ConnectorCatalog,
    ImportEnqueuer,
    ImportRepository,
    SourceRepository,
)


class SourceUsecase:
    def __init__(
        self,
        sources: SourceRepository,
        imports: ImportRepository,
        connectors: ConnectorCatalog,
        enqueue: ImportEnqueuer,
    ) -> None:
        self._sources = sources
        self._imports = imports
        self._connectors = connectors
        self._enqueue = enqueue

    async def register(self, source_type: str, name: str, config: dict[str, Any]) -> Source:
        connector = self._connectors.get(source_type)
        if connector is None:
            raise UnknownConnectorError(source_type)
        try:
            connector.validate_config(config)
        except ConfigValidationError as exc:
            raise ConfigValidationError(str(exc)) from exc
        return await self._sources.add(source_type, name, config)

    async def list_sources(self) -> list[tuple[Source, ImportSnapshot | None]]:
        return await self._sources.list_enabled_with_last_import()

    async def delete(self, source_id: int) -> None:
        source = await self._sources.get_enabled(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        await self._sources.set_enabled(source_id, False)

    async def get(self, source_id: int) -> Source:
        source = await self._sources.get_enabled(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        return source

    async def update(
        self,
        source_id: int,
        name: str | None,
        config_patch: dict[str, Any] | None,
        resources_patch: dict[str, list[dict[str, Any]]] | None,
    ) -> Source:
        source = await self.get(source_id)
        next_name = name.strip() if name is not None else source.name
        if not next_name:
            raise ConfigValidationError("project name must not be empty")
        next_config = dict(source.config)
        if config_patch is not None:
            next_config.update(config_patch)
        if resources_patch is not None:
            resources = dict(next_config.get("resources", {}))
            resources.update(resources_patch)
            next_config["resources"] = resources
        connector = self._connectors.get(source.type)
        if connector is None:
            raise UnknownConnectorError(source.type)
        try:
            connector.validate_config(next_config)
        except ConfigValidationError as exc:
            raise ConfigValidationError(str(exc)) from exc
        return await self._sources.update(source_id, next_name, next_config)

    async def file_count(self, source_id: int) -> int:
        await self.get(source_id)
        return await self._sources.count_imported_files(source_id)

    async def enqueue_import(self, source_id: int) -> str:
        source = await self._sources.get_enabled(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        return self._enqueue(source_id)

    async def import_status(self, source_id: int) -> ImportSnapshot:
        source = await self._sources.get_any(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        latest = await self._imports.latest_for_source(source_id)
        if latest is None:
            raise ImportNotFoundError(source_id)
        return ImportSnapshot(
            status=latest.status,
            progress=latest.progress,
            error=latest.error,
            finished_at=latest.finished_at,
        )
