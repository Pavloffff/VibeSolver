from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.domain.entities import RawItem, StoredSnapshotFile, UnknownConnectorError
from app.domain.repositories import (
    ConnectorCatalog,
    ImportFileRepository,
    SourceSnapshotRepository,
    default_connector_catalog,
)
from app.domain.storage import S3Like, StorageStrategy, resolve_storage_strategy


@dataclass(slots=True)
class ImportContext:
    source_id: int
    source_type: str
    source_config: dict[str, Any]
    import_id: int | None = None
    items: list[RawItem] = field(default_factory=list)


class PipelineStage:
    def run(self, ctx: ImportContext) -> None:
        raise NotImplementedError


class FetchItems(PipelineStage):
    def __init__(self, catalog: ConnectorCatalog | None = None) -> None:
        self._catalog = catalog

    def run(self, ctx: ImportContext) -> None:
        catalog = self._catalog if self._catalog is not None else default_connector_catalog()
        connector = catalog.get(ctx.source_type)
        if connector is None:
            raise UnknownConnectorError(ctx.source_type)
        ctx.items = list(connector.fetch_snapshot(ctx.source_config))


class PersistItems(PipelineStage):
    def __init__(
        self,
        repository: ImportFileRepository | None = None,
        s3: S3Like | None = None,
        bucket: str | None = None,
        strategy: StorageStrategy | None = None,
        snapshot_repository: SourceSnapshotRepository | None = None,
    ) -> None:
        self._repository = repository
        self._s3 = s3
        self._bucket = bucket
        self._strategy = strategy
        self._snapshot_repository = snapshot_repository

    def run(self, ctx: ImportContext) -> None:
        repository = self._repository
        s3 = self._s3
        bucket = self._bucket
        if repository is None or s3 is None or bucket is None:
            raise RuntimeError("PersistItems requires repository, s3 client and bucket")
        strategy = self._strategy
        if strategy is None:
            strategy = resolve_storage_strategy(ctx.source_type, ctx.source_config)
        persisted_files = strategy.persist(
            source_id=ctx.source_id,
            items=ctx.items,
            s3=s3,
            bucket=bucket,
        )
        snapshot_files: list[dict[str, object]] = []
        for persisted_file in persisted_files:
            repository.upsert_file(
                source_id=ctx.source_id,
                path=persisted_file.path,
                branch=persisted_file.branch,
                storage_key=persisted_file.storage_key,
                size_bytes=persisted_file.size_bytes,
                content_hash=persisted_file.content_hash,
            )
            snapshot_files.append(
                {
                    "path": persisted_file.path,
                    "branch": persisted_file.branch,
                    "size_bytes": persisted_file.size_bytes,
                    "storage_key": persisted_file.storage_key,
                    "content_hash": persisted_file.content_hash,
                    "metadata_json": persisted_file.metadata,
                }
            )
        if ctx.import_id is not None and self._snapshot_repository is not None:
            branches = sorted({file.branch for file in persisted_files if file.branch})
            commits = {
                str(file.metadata["branch"]): str(file.metadata["commit_sha"])
                for file in persisted_files
                if file.metadata.get("branch") and file.metadata.get("commit_sha")
            }
            self._snapshot_repository.create_snapshot(
                source_id=ctx.source_id,
                import_id=ctx.import_id,
                files=snapshot_files,
                source_revision={"scope": "code", "branches": branches, "commits": commits},
            )


def load_latest_source_snapshot(
    source_id: int,
    repository: SourceSnapshotRepository,
    s3: S3Like,
    bucket: str,
) -> list[RawItem]:
    stored_files: list[StoredSnapshotFile] = repository.latest_snapshot_files(source_id)
    return _load_snapshot_files(stored_files, s3, bucket)


def load_source_snapshot(
    snapshot_id: int,
    repository: SourceSnapshotRepository,
    s3: S3Like,
    bucket: str,
) -> list[RawItem]:
    return _load_snapshot_files(repository.snapshot_files(snapshot_id), s3, bucket)


def _load_snapshot_files(
    stored_files: list[StoredSnapshotFile], s3: S3Like, bucket: str
) -> list[RawItem]:
    items: list[RawItem] = []
    for stored_file in stored_files:
        response = s3.get_object(Bucket=bucket, Key=stored_file.storage_key)
        body = response["Body"].read()
        items.append(
            RawItem(
                path=stored_file.path,
                content=body,
                meta={
                    **stored_file.metadata,
                    "branch": stored_file.branch,
                    "content_hash": stored_file.content_hash,
                    "size": stored_file.size_bytes,
                },
            )
        )
    return items


STAGE_REGISTRY: list[type[PipelineStage]] = [FetchItems, PersistItems]


def run_stages(
    ctx: ImportContext,
    stages: Sequence[PipelineStage],
    on_stage_done: Callable[[int, int], None] | None = None,
) -> None:
    total = len(stages)
    for index, stage in enumerate(stages):
        stage.run(ctx)
        if on_stage_done is not None:
            on_stage_done(index + 1, total)


__all__ = [
    "STAGE_REGISTRY",
    "FetchItems",
    "ImportContext",
    "PersistItems",
    "PipelineStage",
    "run_stages",
]
