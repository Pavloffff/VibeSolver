from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter.config import get_settings
from app.adapter.db import get_session
from app.adapter.model_providers.providers import build_provider_registry
from app.adapter.repositories import ModelProviderSqlRepository, SourceSqlRepository
from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import (
    ProviderConnection,
    ProviderModel,
    ProviderUnavailableError,
    WorkspaceModelEntry,
)
from app.handler.schemas import (
    ModelOut,
    ModelProviderCreate,
    ModelProviderOut,
    ModelProviderTypeOut,
    ModelProviderUpdate,
    ModelSelectionOut,
    ModelSelectionUpdate,
    OllamaPullIn,
    ProviderAvailableModelOut,
    ProviderModelAdd,
)
from app.usecase.model_providers import (
    ModelProviderNotFoundError,
    ModelProviderUsecase,
    ModelProviderValidationError,
)

router = APIRouter(prefix="/models", tags=["models"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def build_usecase(session: AsyncSession) -> ModelProviderUsecase:
    settings = get_settings()
    return ModelProviderUsecase(
        models=ModelProviderSqlRepository(session, settings.model_secrets_key),
        sources=SourceSqlRepository(session),
        providers=build_provider_registry(settings),
        request_timeout=settings.provider_request_timeout_seconds,
    )


@router.get("/providers/catalog", response_model=list[ModelProviderTypeOut])
async def provider_catalog() -> list[ModelProviderTypeOut]:
    return [
        ModelProviderTypeOut(
            provider_type=provider_type,
            display_name=definition.display_name,
            default_url=definition.default_url,
            requires_api_key=definition.requires_api_key,
            fixed_url=definition.fixed_url,
            sync_all_models=definition.sync_all_models,
            supports_model_pull=definition.supports_model_pull,
        )
        for provider_type, definition in build_provider_registry().items()
    ]


@router.get("/providers", response_model=list[ModelProviderOut])
async def list_providers(session: SessionDep) -> list[ModelProviderOut]:
    return [_provider_out(item) for item in await build_usecase(session).list_connections()]


@router.post("/providers/test")
async def test_provider(payload: ModelProviderCreate, session: SessionDep) -> dict[str, int | str]:
    try:
        count = await build_usecase(session).test_connection(
            payload.provider_type, payload.name, payload.base_url, payload.api_key
        )
    except ModelProviderValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "connected", "available_models": count}


@router.post("/providers", status_code=201, response_model=ModelProviderOut)
async def create_provider(payload: ModelProviderCreate, session: SessionDep) -> ModelProviderOut:
    try:
        connection = await build_usecase(session).create_connection(
            payload.provider_type, payload.name, payload.base_url, payload.api_key
        )
    except ModelProviderValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _provider_out(connection)


@router.post("/providers/{connection_id}/test")
async def test_saved_provider(connection_id: int, session: SessionDep) -> dict[str, int | str]:
    try:
        count = await build_usecase(session).test_saved_connection(connection_id)
    except ModelProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model provider not found") from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "connected", "available_models": count}


@router.patch("/providers/{connection_id}", response_model=ModelProviderOut)
async def update_provider(
    connection_id: int, payload: ModelProviderUpdate, session: SessionDep
) -> ModelProviderOut:
    try:
        connection = await build_usecase(session).update_connection(
            connection_id, payload.name, payload.base_url, payload.api_key
        )
    except ModelProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model provider not found") from exc
    except ModelProviderValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _provider_out(connection)


@router.delete("/providers/{connection_id}", status_code=204)
async def delete_provider(connection_id: int, session: SessionDep) -> None:
    try:
        await build_usecase(session).delete_connection(connection_id)
    except ModelProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model provider not found") from exc


@router.get("/providers/{connection_id}/available", response_model=list[ProviderAvailableModelOut])
async def available_models(
    connection_id: int,
    session: SessionDep,
    capability: str | None = Query(default=None),
) -> list[ProviderAvailableModelOut]:
    try:
        models = await build_usecase(session).available_models(connection_id)
    except ModelProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model provider not found") from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if capability is not None:
        models = [model for model in models if capability in model.capabilities]
    return [_available_model_out(model) for model in models]


@router.post("/providers/{connection_id}/sync", response_model=list[ModelOut])
async def sync_models(connection_id: int, session: SessionDep) -> list[ModelOut]:
    try:
        models = await build_usecase(session).sync_models(connection_id)
    except ModelProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model provider not found") from exc
    except ModelProviderValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [_model_out(model) for model in models]


@router.post("/providers/{connection_id}/models", response_model=ModelOut)
async def add_model(connection_id: int, payload: ProviderModelAdd, session: SessionDep) -> ModelOut:
    try:
        model = await build_usecase(session).add_model(connection_id, payload.provider_model_id)
    except ModelProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model provider not found") from exc
    except ModelProviderValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _model_out(model)


@router.post("/providers/{connection_id}/models/pull")
async def pull_ollama_model(
    connection_id: int, payload: OllamaPullIn, session: SessionDep
) -> StreamingResponse:
    try:
        stream = build_usecase(session).pull_ollama_model(connection_id, payload.model_id)
    except ModelProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model provider not found") from exc
    return StreamingResponse(stream, media_type="application/x-ndjson")


@router.get("", response_model=list[ModelOut])
async def list_models(
    session: SessionDep,
    capability: str | None = Query(default=None),
) -> list[ModelOut]:
    models = await build_usecase(session).list_models()
    if capability is not None:
        models = [model for model in models if capability in model.capabilities]
    return [_model_out(model) for model in models]


@router.delete("/{model_id}", status_code=204)
async def delete_model(model_id: int, session: SessionDep) -> None:
    try:
        await build_usecase(session).delete_model(model_id)
    except ModelProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model not found") from exc


@router.get("/projects/{source_id}/selections", response_model=ModelSelectionOut)
async def get_project_model_selections(source_id: int, session: SessionDep) -> ModelSelectionOut:
    try:
        selections = await build_usecase(session).project_selections(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return ModelSelectionOut(
        indexing=selections.get("indexing"),
        documentation_generation=selections.get("documentation_generation"),
    )


@router.put("/projects/{source_id}/selections/{role}", response_model=ModelSelectionOut)
async def set_project_model_selection(
    source_id: int,
    role: str,
    payload: ModelSelectionUpdate,
    session: SessionDep,
) -> ModelSelectionOut:
    try:
        selections = await build_usecase(session).set_project_selection(
            source_id, role, payload.model_id
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ModelProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model not found") from exc
    except ModelProviderValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ModelSelectionOut(
        indexing=selections.get("indexing"),
        documentation_generation=selections.get("documentation_generation"),
    )


def _provider_out(connection: ProviderConnection) -> ModelProviderOut:
    return ModelProviderOut(
        id=connection.id,
        provider_type=connection.provider_type,
        name=connection.name,
        base_url=connection.base_url,
        has_api_key=connection.has_api_key,
    )


def _available_model_out(model: ProviderModel) -> ProviderAvailableModelOut:
    return ProviderAvailableModelOut(
        provider_model_id=model.provider_model_id,
        display_name=model.display_name,
        capabilities=model.capabilities,
        status=model.status,
        progress=model.progress,
        metadata=model.metadata,
    )


def _model_out(model: WorkspaceModelEntry) -> ModelOut:
    return ModelOut(
        id=model.id,
        provider_connection_id=model.provider_connection_id,
        provider_type=model.provider_type,
        provider_name=model.provider_name,
        provider_model_id=model.provider_model_id,
        display_name=model.display_name,
        capabilities=model.capabilities,
        status=model.status,
        progress=model.progress,
        metadata=model.metadata,
    )
