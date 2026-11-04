from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.domain.entities import RawItem
from app.domain.models import Import, ImportState


@dataclass(slots=True)
class ImportContext:
    source_id: int
    source_type: str
    source_config: dict[str, Any]
    items: list[RawItem] = field(default_factory=list)


class PipelineStage:
    def run(self, ctx: ImportContext) -> None:
        raise NotImplementedError


class FetchItems(PipelineStage):
    def run(self, ctx: ImportContext) -> None:
        raise NotImplementedError


class PersistItems(PipelineStage):
    def run(self, ctx: ImportContext) -> None:
        raise NotImplementedError


STAGE_REGISTRY: list[type[PipelineStage]] = []


class SyncImportRunner:
    def __init__(self, session_factory: Any, stages: list[PipelineStage] | None = None) -> None:
        self._session_factory = session_factory
        self._stages = stages or [stage() for stage in STAGE_REGISTRY]

    def run(self, source_id: int) -> None:
        with self._session_factory() as session:
            import_row = Import(
                source_id=source_id,
                status=ImportState.RUNNING.value,
                progress=0,
                started_at=datetime.now(UTC),
            )
            session.add(import_row)
            session.flush()
            import_row.status = ImportState.DONE.value
            import_row.progress = 100
            import_row.finished_at = datetime.now(UTC)
            session.commit()


__all__ = [
    "STAGE_REGISTRY",
    "FetchItems",
    "ImportContext",
    "PersistItems",
    "PipelineStage",
    "SyncImportRunner",
]
