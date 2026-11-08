import mimetypes
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter import celery_tasks, indexing_tasks
from app.adapter.config import get_settings
from app.adapter.connectors import ConnectorCatalogImpl
from app.adapter.db import get_session
from app.adapter.material_generation import MaterialGenerationAdapter
from app.adapter.repositories import (
    ImportSqlRepository,
    IndexingSqlRepository,
    IndexSearchSqlRepository,
    ModelProviderSqlRepository,
    SourceResourceSnapshotSqlRepository,
    SourceSqlRepository,
)
from app.adapter.s3 import make_s3_client
from app.domain.entities import (
    ConfigValidationError,
    ImportNotFoundError,
    SourceNotFoundError,
    UnknownConnectorError,
)
from app.domain.model_provider_entities import ProviderUnavailableError
from app.handler.schemas import (
    DocumentationImportOut,
    ImportEnqueueOut,
    ImportStatusOut,
    IndexEnqueueOut,
    IndexRunOut,
    LastImportOut,
    MaterialGenerationIn,
    MaterialGenerationOut,
    ProjectIndexStatusOut,
    ResourceContentOut,
    ResourceContentUpdate,
    SourceCreate,
    SourceOut,
    SourceStatsOut,
    SourceUpdate,
    sanitize_config,
)
from app.usecase.documentation_fs import (
    DocumentationPathError,
    is_supported_archive,
    normalize_documentation_path,
    unpack_archive,
)
from app.usecase.indexing import IndexingUsecase
from app.usecase.material_generation import (
    MaterialGenerationConfig,
    MaterialGenerationConflictError,
    MaterialGenerationResponseError,
    MaterialGenerationUnavailableError,
    MaterialGenerationUsecase,
)
from app.usecase.project_resources import ProjectResourceNotFoundError, ProjectResourceUsecase
from app.usecase.sources import SourceUsecase

router = APIRouter(prefix="/sources", tags=["sources"])
READ_CHUNK_BYTES = 1024 * 1024

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def enqueue(source_id: int) -> str:
    try:
        result = celery_tasks.run_source_import.delay(source_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="task queue unavailable") from exc
    return str(result.id)


def enqueue_index(run_id: int) -> str:
    try:
        result = indexing_tasks.run_project_index_task.delay(run_id)
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
    async def invalidate_indexes(source_id: int, index_types: list[str]) -> None:
        await refresh_resource_snapshots(session, source_id, index_types)

    return ProjectResourceUsecase(
        sources=SourceSqlRepository(session),
        s3=make_s3_client(get_settings()),
        bucket=get_settings().s3_bucket_raw,
        invalidate_indexes=invalidate_indexes,
    )


async def refresh_resource_snapshots(
    session: AsyncSession, source_id: int, index_types: list[str]
) -> None:
    if not index_types:
        return
    await IndexingSqlRepository(session).mark_stale(source_id, index_types)
    source = await SourceSqlRepository(session).get_any(source_id)
    if source is None:
        return
    resources = source.config.get("resources", {})
    if not isinstance(resources, dict):
        resources = {}
    settings = get_settings()
    snapshots = SourceResourceSnapshotSqlRepository(
        session, make_s3_client(settings), settings.s3_bucket_raw
    )
    for index_type in index_types:
        category = "documentation" if index_type == "documentation" else "user_flow"
        entries = resources.get(category, [])
        if not isinstance(entries, list):
            entries = []
        await snapshots.create_snapshot(source_id, index_type, entries)


def build_indexing_usecase(session: AsyncSession) -> IndexingUsecase:
    settings = get_settings()
    return IndexingUsecase(
        sources=SourceSqlRepository(session),
        imports=ImportSqlRepository(session),
        models=ModelProviderSqlRepository(session, settings.model_secrets_key),
        indexes=IndexingSqlRepository(session),
        resource_snapshots=SourceResourceSnapshotSqlRepository(
            session, make_s3_client(settings), settings.s3_bucket_raw
        ),
        enqueue=enqueue_index,
    )


def build_material_generation_usecase(session: AsyncSession) -> MaterialGenerationUsecase:
    settings = get_settings()
    return MaterialGenerationUsecase(
        sources=SourceSqlRepository(session),
        models=ModelProviderSqlRepository(session, settings.model_secrets_key),
        indexes=build_indexing_usecase(session),
        search=IndexSearchSqlRepository(session),
        gateway=MaterialGenerationAdapter(),
        resources=build_resource_usecase(session),
        config=MaterialGenerationConfig(
            timeout_seconds=settings.material_generation_timeout_seconds,
            max_output_tokens=settings.material_generation_max_output_tokens,
            context_chunks=settings.material_generation_context_chunks,
            max_context_characters=settings.material_generation_max_context_characters,
            max_files=settings.material_generation_max_files,
            max_file_bytes=settings.material_generation_max_file_bytes,
            max_total_bytes=settings.material_generation_max_total_bytes,
        ),
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
async def update_source(source_id: int, payload: SourceUpdate, session: SessionDep) -> SourceOut:
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
        if resources is not None:
            changed_indexes = [
                index_type
                for category, index_types in {
                    "documentation": ["documentation", "user_flow"],
                    "user_flow": ["user_flow"],
                }.items()
                if category in resources
                for index_type in index_types
            ]
            await refresh_resource_snapshots(session, source_id, changed_indexes)
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


@router.get("/{source_id}/indexes", response_model=ProjectIndexStatusOut)
async def get_index_status(source_id: int, session: SessionDep) -> ProjectIndexStatusOut:
    try:
        state = await build_indexing_usecase(session).status(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    return ProjectIndexStatusOut(
        ready=state.ready,
        import_status=state.import_status,
        indexes=[
            IndexRunOut(
                index_type=item.index_type,
                status=item.status,
                progress=item.progress,
                run_id=item.run_id,
                snapshot_id=item.snapshot_id,
                files_total=item.files_total,
                chunks_total=item.chunks_total,
                error=item.error,
                updated_at=item.updated_at.isoformat() if item.updated_at else None,
            )
            for item in state.indexes
        ],
    )


@router.post("/{source_id}/indexes/{index_type}", status_code=202, response_model=IndexEnqueueOut)
async def enqueue_indexing(source_id: int, index_type: str, session: SessionDep) -> IndexEnqueueOut:
    try:
        run_id, task_id = await build_indexing_usecase(session).queue(source_id, index_type)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return IndexEnqueueOut(run_id=run_id, task_id=task_id, status="queued")


@router.post(
    "/{source_id}/materials/generate",
    response_model=MaterialGenerationOut,
    status_code=201,
    responses={
        409: {"description": "Required indexes or model configuration are not ready"},
        502: {"description": "The selected model failed to return a valid response"},
    },
)
async def generate_project_materials(
    source_id: int, payload: MaterialGenerationIn, session: SessionDep
) -> MaterialGenerationOut:
    try:
        resources = await build_material_generation_usecase(session).generate(
            source_id, payload.category, payload.instructions
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except MaterialGenerationConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "generated files conflict with existing local resources",
                "conflicts": exc.conflicts,
            },
        ) from exc
    except MaterialGenerationUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MaterialGenerationResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return MaterialGenerationOut(resources=resources)


@router.post("/{source_id}/resources/import", response_model=DocumentationImportOut)
@router.post("/{source_id}/documentation/import", response_model=DocumentationImportOut)
async def import_documentation(
    source_id: int,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    parent_path: Annotated[str, Form()] = "",
    category: Annotated[str, Form()] = "documentation",
    origin: Annotated[str, Form()] = "uploaded",
) -> DocumentationImportOut:
    settings = get_settings()
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(READ_CHUNK_BYTES):
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="upload too large")
        chunks.append(chunk)
    data = b"".join(chunks)
    filename = PurePosixPath((file.filename or "").replace("\\", "/")).name
    if not filename:
        raise HTTPException(status_code=422, detail="file name is required")
    try:
        parent = normalize_documentation_path(parent_path) if parent_path else ""
        if is_supported_archive(data):
            unpacked = unpack_archive(filename, data, settings.max_archive_unpacked_bytes)
            files = {
                normalize_documentation_path(f"{parent}/{path}" if parent else path): body
                for path, body in unpacked.items()
            }
        else:
            path = normalize_documentation_path(f"{parent}/{filename}" if parent else filename)
            if path.casefold().endswith(".md"):
                try:
                    data.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise HTTPException(
                        status_code=422, detail="Markdown file must use UTF-8 encoding"
                    ) from exc
            files = {path: data}
    except DocumentationPathError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    content_types = {
        path: mimetypes.guess_type(path)[0] or "application/octet-stream" for path in files
    }
    try:
        result = await build_resource_usecase(session).import_documentation(
            source_id, files, content_types, category, origin
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    if result["conflicts"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "documentation paths already exist with different content",
                "conflicts": result["conflicts"],
            },
        )
    return DocumentationImportOut(**result)


@router.delete("/{source_id}/resources/folder", status_code=204)
@router.delete("/{source_id}/documentation/folder", status_code=204)
async def delete_documentation_folder(
    source_id: int, path: str, session: SessionDep, category: str = "documentation"
) -> None:
    try:
        safe_path = normalize_documentation_path(path)
        await build_resource_usecase(session).delete_documentation_folder(
            source_id, safe_path, category
        )
    except DocumentationPathError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ProjectResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Documentation folder not found") from exc


@router.get("/{source_id}/resources/{category}/{resource_id}", response_model=ResourceContentOut)
async def get_markdown_resource(
    source_id: int, category: str, resource_id: str, session: SessionDep
) -> ResourceContentOut:
    try:
        content = await build_resource_usecase(session).read_markdown(
            source_id, category, resource_id
        )
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


@router.post(
    "/{source_id}/resources/user_flow/{resource_id}/approve",
    response_model=ResourceContentOut,
)
async def approve_user_flow_resource(
    source_id: int, resource_id: str, session: SessionDep
) -> ResourceContentOut:
    try:
        content = await build_resource_usecase(session).approve_user_flow(source_id, resource_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ProjectResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="User Flow resource not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ResourceContentOut(content=content)


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
