from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter.config import get_settings
from app.adapter.db import get_session
from app.adapter.material_generation import MaterialGenerationAdapter
from app.adapter.repositories import (
    IndexingSqlRepository,
    IndexSearchSqlRepository,
    ModelProviderSqlRepository,
    SourceSqlRepository,
)
from app.adapter.rerank import build_rerank_gateway
from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import ProviderUnavailableError
from app.domain.repositories.retrieval import SearchResponse, SearchUnavailableError
from app.handler.schemas import SearchHitOut, SearchIn, SearchMetaOut, SearchOut
from app.usecase.retrieval import RetrievalUsecase

router = APIRouter(prefix="/sources", tags=["search"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def build_retrieval_usecase(session: AsyncSession) -> RetrievalUsecase:
    settings = get_settings()
    return RetrievalUsecase(
        sources=SourceSqlRepository(session),
        indexes=IndexingSqlRepository(session),
        search=IndexSearchSqlRepository(session),
        models=ModelProviderSqlRepository(session, settings.model_secrets_key),
        embed=MaterialGenerationAdapter().embed_queries,
        rerank=build_rerank_gateway(settings),
        request_timeout=settings.provider_request_timeout_seconds,
    )


@router.post("/{source_id}/search", response_model=SearchOut)
async def search_project(
    source_id: int, payload: SearchIn, session: SessionDep
) -> SearchOut:
    try:
        response = await build_retrieval_usecase(session).search(
            source_id, payload.query, payload.index_types, payload.top_k
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except SearchUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _search_out(response)


def _search_out(response: SearchResponse) -> SearchOut:
    return SearchOut(
        results=[
            SearchHitOut(
                index_type=hit.index_type,
                run_id=hit.run_id,
                path=hit.path,
                branch=hit.branch,
                start_line=hit.start_line,
                end_line=hit.end_line,
                symbol=hit.symbol,
                content=hit.content,
                score=hit.score,
                rerank_score=hit.rerank_score,
                source_ref=hit.source_ref,
            )
            for hit in response.hits
        ],
        meta=SearchMetaOut(
            indexes_searched=response.meta.indexes_searched,
            top_k=response.meta.top_k,
            candidate_k=response.meta.candidate_k,
            rerank_applied=response.meta.rerank_applied,
            warnings=response.meta.warnings,
            latency_ms=response.meta.latency_ms,
        ),
    )
