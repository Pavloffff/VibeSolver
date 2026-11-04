from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter import celery_tasks
from app.adapter.connectors import ConnectorCatalogImpl
from app.adapter.db import get_session
from app.adapter.repositories import ImportSqlRepository, SourceSqlRepository
from app.domain.entities import (
    ConfigValidationError,
    ImportNotFoundError,
    SourceNotFoundError,
    UnknownConnectorError,
)
from app.handler.schemas import (
    ImportEnqueueOut,
    ImportStatusOut,
    LastImportOut,
    SourceCreate,
    SourceOut,
    sanitize_config,
)
from app.usecase.sources import SourceUsecase

router = APIRouter(prefix="/sources", tags=["sources"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def enqueue(source_id: int) -> str:
    try:
        result = celery_tasks.run_source_import.delay(source_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="task queue unavailable") from exc
    return str(result.id)


def build_usecase(session: AsyncSession) -> SourceUsecase:
    return SourceUsecase(
        sources=SourceSqlRepository(session),
        imports=ImportSqlRepository(session),
        connectors=ConnectorCatalogImpl(),
        enqueue=enqueue,
    )


@router.post("", status_code=201, response_model=SourceOut)
async def create_source(payload: SourceCreate, session: SessionDep) -> SourceOut:
    usecase = build_usecase(session)
    try:
        source = await usecase.register(payload.type, payload.name, payload.config)
    except UnknownConnectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ConfigValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SourceOut(
        id=source.id,
        type=source.type,
        name=source.name,
        enabled=source.enabled,
        config=sanitize_config(source.config),
        last_import=None,
    )


@router.get("", response_model=list[SourceOut])
async def list_sources(session: SessionDep) -> list[SourceOut]:
    usecase = build_usecase(session)
    items = await usecase.list_sources()
    return [
        SourceOut(
            id=source.id,
            type=source.type,
            name=source.name,
            enabled=source.enabled,
            config=sanitize_config(source.config),
            last_import=(
                LastImportOut(
                    status=snapshot.status,
                    finished_at=(
                        snapshot.finished_at.isoformat()
                        if snapshot.finished_at is not None
                        else None
                    ),
                )
                if snapshot is not None
                else None
            ),
        )
        for source, snapshot in items
    ]


@router.delete("/{source_id}", status_code=204)
async def delete_source(source_id: int, session: SessionDep) -> None:
    usecase = build_usecase(session)
    try:
        await usecase.delete(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="source not found") from exc


@router.post("/{source_id}/import", status_code=202, response_model=ImportEnqueueOut)
async def enqueue_import(source_id: int, session: SessionDep) -> ImportEnqueueOut:
    usecase = build_usecase(session)
    try:
        task_id = await usecase.enqueue_import(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="source not found") from exc
    return ImportEnqueueOut(task_id=task_id)


@router.get("/{source_id}/import", response_model=ImportStatusOut)
async def get_import_status(source_id: int, session: SessionDep) -> ImportStatusOut:
    usecase = build_usecase(session)
    try:
        snapshot = await usecase.import_status(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="source not found") from exc
    except ImportNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="no import has been started for this source"
        ) from exc
    return ImportStatusOut(status=snapshot.status, progress=snapshot.progress, error=snapshot.error)
