from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.adapter.celery_app import celery_app
from app.adapter.config import Settings, get_settings
from app.adapter.connectors import ConnectorCatalogImpl
from app.adapter.db import to_sync_dsn
from app.adapter.repositories import ImportFileSqlRepository, SourceSnapshotSqlRepository
from app.adapter.s3 import make_s3_client
from app.domain.entities import SourceNotFoundError
from app.domain.models import Import, ImportState, Source
from app.usecase.import_pipeline import (
    STAGE_REGISTRY,
    FetchItems,
    ImportContext,
    PersistItems,
    PipelineStage,
    run_stages,
)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_worker_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(to_sync_dsn(get_settings().database_url))
    return _engine


def get_worker_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_worker_engine(), expire_on_commit=False)
    return _session_factory


def _stage_wiring_kwargs(
    stage_cls: type[PipelineStage], session: Session, settings: Settings
) -> dict[str, Any]:
    if stage_cls is FetchItems:
        return {"catalog": ConnectorCatalogImpl()}
    if stage_cls is PersistItems:
        return {
            "repository": ImportFileSqlRepository(session),
            "snapshot_repository": SourceSnapshotSqlRepository(session),
            "s3": make_s3_client(settings),
            "bucket": settings.s3_bucket_raw,
        }
    return {}


def _build_stages(session: Session, settings: Settings) -> list[PipelineStage]:
    return [
        stage_cls(**_stage_wiring_kwargs(stage_cls, session, settings))
        for stage_cls in STAGE_REGISTRY
    ]


def _run_source_import(source_id: int) -> None:
    settings = get_settings()
    session_factory = get_worker_session_factory()
    with session_factory() as session:
        source = session.get(Source, source_id)
        if source is None:
            raise SourceNotFoundError(f"source not found: {source_id}")
        import_row = Import(
            source_id=source_id,
            status=ImportState.RUNNING.value,
            progress=0,
            started_at=datetime.now(UTC),
        )
        session.add(import_row)
        session.commit()

        def update_progress(done: int, total: int) -> None:
            import_row.progress = int(done * 100 / total)
            session.commit()

        try:
            ctx = ImportContext(
                source_id=source_id,
                source_type=source.type,
                source_config=source.config,
                import_id=import_row.id,
            )
            run_stages(ctx, _build_stages(session, settings), on_stage_done=update_progress)
        except Exception as exc:
            session.rollback()
            import_row.status = ImportState.FAILED.value
            import_row.progress = 0
            import_row.error = str(exc)
            import_row.finished_at = datetime.now(UTC)
            session.commit()
            raise
        import_row.status = ImportState.DONE.value
        import_row.progress = 100
        import_row.finished_at = datetime.now(UTC)
        session.commit()


run_source_import: Any = celery_app.task(name="vibesolver.import.run_source_import")(
    _run_source_import
)
