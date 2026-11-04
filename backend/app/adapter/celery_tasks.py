from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.adapter.celery_app import celery_app
from app.adapter.config import get_settings
from app.adapter.db import to_sync_dsn
from app.usecase.import_pipeline import SyncImportRunner

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


def _run_source_import(source_id: int) -> None:
    runner = SyncImportRunner(get_worker_session_factory())
    runner.run(source_id)


run_source_import: Any = celery_app.task(name="vibesolver.import.run_source_import")(
    _run_source_import
)
