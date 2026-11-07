from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter import celery_tasks
from app.adapter.config import get_settings
from app.adapter.connectors import ConnectorCatalogImpl
from app.adapter.db import get_session
from app.adapter.repositories import ImportSqlRepository, SourceSqlRepository
from app.adapter.s3 import make_s3_client
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
    ResourceContentOut,
    ResourceContentUpdate,
    SourceCreate,
    SourceOut,
    SourceStatsOut,
    SourceUpdate,
    sanitize_config,
)
from app.usecase.project_resources import ProjectResourceNotFoundError, ProjectResourceUsecase
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


def build_resource_usecase(session: AsyncSession) -> ProjectResourceUsecase:
    settings = get_settings()
    return ProjectResourceUsecase(
        sources=SourceSqlRepository(session),
        s3=make_s3_client(settings),
        bucket=settings.s3_bucket_raw,
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


@router.get("/{source_id}", response_model=SourceOut)
async def get_source(source_id: int, session: SessionDep) -> SourceOut:
    usecase = build_usecase(session)
    try:
        source = await usecase.get(source_id)
        snapshot = await usecase.import_status(source_id)
    except ImportNotFoundError:
        snapshot = None
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    return SourceOut(
        id=source.id,
        type=source.type,
        name=source.name,
        enabled=source.enabled,
        config=sanitize_config(source.config),
        last_import=(
            LastImportOut(
                status=snapshot.status,
                finished_at=(snapshot.finished_at.isoformat() if snapshot.finished_at else None),
            )
            if snapshot is not None
            else None
        ),
    )


@router.patch("/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: int, payload: SourceUpdate, session: SessionDep
) -> SourceOut:
    usecase = build_usecase(session)
    resources = (
        {
            category: [resource.model_dump() for resource in entries]
            for category, entries in payload.resources.items()
        }
        if payload.resources is not None
        else None
    )
    try:
        source = await usecase.update(source_id, payload.name, payload.config, resources)
        snapshot = await usecase.import_status(source_id)
    except ImportNotFoundError:
        snapshot = None
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except (ConfigValidationError, UnknownConnectorError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SourceOut(
        id=source.id,
        type=source.type,
        name=source.name,
        enabled=source.enabled,
        config=sanitize_config(source.config),
        last_import=(
            LastImportOut(
                status=snapshot.status,
                finished_at=(snapshot.finished_at.isoformat() if snapshot.finished_at else None),
            )
            if snapshot is not None
            else None
        ),
    )


@router.get("/{source_id}/stats", response_model=SourceStatsOut)
async def get_source_stats(source_id: int, session: SessionDep) -> SourceStatsOut:
    try:
        count = await build_usecase(session).file_count(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    return SourceStatsOut(file_count=count)


@router.get("/{source_id}/resources/{category}/{resource_id}", response_model=ResourceContentOut)
async def get_markdown_resource(
    source_id: int, category: str, resource_id: str, session: SessionDep
) -> ResourceContentOut:
    try:
        content = await build_resource_usecase(session).read_markdown(source_id, category, resource_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ProjectResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Markdown resource not found") from exc
    return ResourceContentOut(content=content)


@router.patch("/{source_id}/resources/{category}/{resource_id}", status_code=204)
async def update_markdown_resource(
    source_id: int,
    category: str,
    resource_id: str,
    payload: ResourceContentUpdate,
    session: SessionDep,
) -> None:
    try:
        await build_resource_usecase(session).update_markdown(
            source_id, category, resource_id, payload.content
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ProjectResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Markdown resource not found") from exc


@router.delete("/{source_id}/resources/{category}/{resource_id}", status_code=204)
async def delete_project_resource(
    source_id: int, category: str, resource_id: str, session: SessionDep
) -> None:
    try:
        await build_resource_usecase(session).delete_resource(source_id, category, resource_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ProjectResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project resource not found") from exc


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
