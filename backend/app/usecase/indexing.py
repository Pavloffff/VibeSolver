from collections.abc import Callable
from dataclasses import dataclass, replace

from app.domain.entities import SourceNotFoundError
from app.domain.repositories import (
    ImportRepository,
    IndexingRepository,
    IndexRunStatus,
    ModelProviderRepository,
    ResourceSnapshotRepository,
    SourceRepository,
)
from app.usecase.code_indexer import AST_CHUNKER_VERSION, AST_PARSER_VERSION
from app.usecase.documentation_indexer import (
    DOCUMENT_CHUNKER_VERSION,
    DOCUMENT_PARSER_VERSION,
)


@dataclass(frozen=True, slots=True)
class IndexerDefinition:
    parser_version: str
    chunker_version: str
    resource_category: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectReadiness:
    ready: bool
    import_status: str
    indexes: list[IndexRunStatus]


INDEXER_REGISTRY: dict[str, IndexerDefinition] = {
    "code": IndexerDefinition(AST_PARSER_VERSION, AST_CHUNKER_VERSION),
    "documentation": IndexerDefinition(
        DOCUMENT_PARSER_VERSION, DOCUMENT_CHUNKER_VERSION, "documentation"
    ),
    "user_flow": IndexerDefinition("flow-json-or-text-v2", "flow-chunker-v2", "user_flow"),
}


class IndexingUsecase:
    def __init__(
        self,
        sources: SourceRepository,
        imports: ImportRepository,
        models: ModelProviderRepository,
        indexes: IndexingRepository,
        resource_snapshots: ResourceSnapshotRepository,
        enqueue: Callable[[int], str],
    ) -> None:
        self._sources = sources
        self._imports = imports
        self._models = models
        self._indexes = indexes
        self._resource_snapshots = resource_snapshots
        self._enqueue = enqueue

    async def queue(self, source_id: int, index_type: str) -> tuple[int, str]:
        definition = INDEXER_REGISTRY.get(index_type)
        if definition is None:
            raise ValueError("unsupported index type")
        source = await self._sources.get_any(source_id)
        if source is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        model_id = await self._indexing_model(source_id)
        snapshot_id = await self._snapshot_id(source_id, index_type, definition.resource_category)
        run_id = await self._indexes.queue_run(
            source_id,
            index_type,
            snapshot_id,
            model_id,
            definition.parser_version,
            definition.chunker_version,
        )
        try:
            task_id = self._enqueue(run_id)
        except Exception as exc:
            await self._indexes.fail_run(run_id, "task queue unavailable")
            raise RuntimeError("task queue unavailable") from exc
        return run_id, task_id

    async def status(self, source_id: int) -> ProjectReadiness:
        if await self._sources.get_any(source_id) is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        latest_import = await self._imports.latest_for_source(source_id)
        import_status = latest_import.status if latest_import is not None else "not_started"
        selected_model_id = (await self._models.get_project_selections(source_id)).get("indexing")
        current = {item.index_type: item for item in await self._indexes.statuses(source_id)}
        indexes = [
            current.get(index_type)
            or IndexRunStatus(index_type, "not_started", 0, None, None, 0, 0, None, None)
            for index_type in INDEXER_REGISTRY
        ]
        indexes = [
            replace(item, status="stale")
            if item.status == "completed"
            and (
                item.parser_version != INDEXER_REGISTRY[item.index_type].parser_version
                or item.chunker_version != INDEXER_REGISTRY[item.index_type].chunker_version
                or item.embedding_model_id != selected_model_id
            )
            else item
            for item in indexes
        ]
        ready = import_status == "done" and all(item.status == "completed" for item in indexes)
        return ProjectReadiness(ready, import_status, indexes)

    async def _snapshot_id(
        self, source_id: int, index_type: str, resource_category: str | None
    ) -> int:
        if resource_category is None:
            snapshot_id = await self._indexes.latest_completed_import_snapshot(source_id)
            if snapshot_id is None:
                raise ValueError("complete the source import before indexing code")
            return snapshot_id
        source = await self._sources.get_any(source_id)
        if source is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        resources = source.config.get("resources", {})
        entries = resources.get(resource_category, []) if isinstance(resources, dict) else []
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"add {resource_category.replace('_', ' ')} files before indexing")
        valid_entries = [item for item in entries if isinstance(item, dict)]
        if not valid_entries:
            raise ValueError(f"add {resource_category.replace('_', ' ')} files before indexing")
        return await self._resource_snapshots.create_snapshot(source_id, index_type, valid_entries)

    async def _indexing_model(self, source_id: int) -> int:
        selections = await self._models.get_project_selections(source_id)
        model_id = selections.get("indexing")
        if model_id is None:
            raise ValueError("select a local embedding model in project settings first")
        model = await self._models.get_model(model_id)
        if model is None or "embedding" not in model.capabilities:
            raise ValueError("selected indexing model does not support embeddings")
        if model.provider_type == "openrouter":
            raise ValueError(
                "indexing source code and project files requires a local embedding model"
            )
        if model.status not in {"available", "installed"}:
            raise ValueError("selected indexing model is not ready")
        return model_id
