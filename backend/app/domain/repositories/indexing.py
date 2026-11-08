from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class IndexRunStatus:
    index_type: str
    status: str
    progress: int
    run_id: int | None
    snapshot_id: int | None
    files_total: int
    chunks_total: int
    error: str | None
    updated_at: datetime | None
    parser_version: str | None = None
    chunker_version: str | None = None
    embedding_model_id: int | None = None


class IndexingRepository(Protocol):
    async def latest_completed_import_snapshot(self, source_id: int) -> int | None: ...

    async def queue_run(
        self,
        source_id: int,
        index_type: str,
        snapshot_id: int,
        embedding_model_id: int,
        parser_version: str,
        chunker_version: str,
    ) -> int: ...

    async def statuses(self, source_id: int) -> list[IndexRunStatus]: ...

    async def fail_run(self, run_id: int, error: str) -> None: ...

    async def mark_stale(self, source_id: int, index_types: list[str]) -> None: ...


class ResourceSnapshotRepository(Protocol):
    async def create_snapshot(
        self, source_id: int, scope: str, resources: list[dict[str, object]]
    ) -> int: ...
