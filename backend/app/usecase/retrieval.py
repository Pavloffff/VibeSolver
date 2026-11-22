import asyncio
import time
from collections.abc import Mapping, Sequence

from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import ProviderCredentials
from app.domain.repositories.indexing import IndexingRepository
from app.domain.repositories.material_generation import (
    IndexSearchRepository,
    RetrievedChunk,
)
from app.domain.repositories.model_providers import ModelProviderRepository
from app.domain.repositories.retrieval import (
    EmbedQueries,
    RerankGateway,
    SearchHit,
    SearchMeta,
    SearchResponse,
    SearchUnavailableError,
)
from app.domain.repositories.sources import SourceRepository
from app.domain.repositories.ticket_log_search import (
    RetrievedTicketLogChunk,
    TicketLogSearchRepository,
)

RRF_K = 60


def rank_with_rrf(
    dense: Sequence[RetrievedChunk], lexical: Sequence[RetrievedChunk]
) -> list[tuple[RetrievedChunk, float]]:
    scores: dict[tuple[str, int], float] = {}
    chunks: dict[tuple[str, int], RetrievedChunk] = {}
    for results in (dense, lexical):
        ordered = sorted(results, key=lambda chunk: chunk.score, reverse=True)
        for rank, chunk in enumerate(ordered, start=1):
            key = (chunk.index_type, chunk.chunk_id)
            chunks[key] = chunk
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
    ranked = sorted(chunks.items(), key=lambda item: scores[item[0]], reverse=True)
    return [(chunk, scores[key]) for key, chunk in ranked]


def rrf_fuse(
    dense: Sequence[RetrievedChunk],
    lexical: Sequence[RetrievedChunk],
    limit: int,
) -> list[RetrievedChunk]:
    return [chunk for chunk, _ in rank_with_rrf(dense, lexical)][:limit]


async def hybrid_search(
    search: IndexSearchRepository,
    source_id: int,
    runs: Mapping[str, int],
    query: str,
    vector: list[float],
    limit: int,
) -> list[tuple[RetrievedChunk, float]]:
    dense: list[RetrievedChunk] = []
    lexical: list[RetrievedChunk] = []
    for index_type, run_id in runs.items():
        dense.extend(await search.search_dense(source_id, index_type, run_id, vector, limit))
        lexical.extend(await search.search_lexical(source_id, index_type, run_id, query, limit))
    return rank_with_rrf(dense, lexical)


class RetrievalUsecase:
    def __init__(
        self,
        sources: SourceRepository,
        indexes: IndexingRepository,
        search: IndexSearchRepository,
        models: ModelProviderRepository,
        embed: EmbedQueries,
        rerank: RerankGateway | None,
        request_timeout: int,
        ticket_log_search: TicketLogSearchRepository | None = None,
    ) -> None:
        self._sources = sources
        self._indexes = indexes
        self._search = search
        self._models = models
        self._embed = embed
        self._rerank = rerank
        self._request_timeout = request_timeout
        self._ticket_log_search = ticket_log_search

    async def search(
        self,
        source_id: int,
        query: str,
        index_types: Sequence[str] | None = None,
        top_k: int = 8,
    ) -> SearchResponse:
        started = time.monotonic()
        normalized_query = query.strip()
        if not normalized_query:
            raise SearchUnavailableError("search query must not be empty")
        if await self._sources.get_any(source_id) is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        runs = await self._active_runs(source_id, index_types)
        credentials, provider_model_id, _model_id = await self._embedding_target(source_id)
        vectors = await asyncio.to_thread(
            self._embed, credentials, provider_model_id, [normalized_query], self._request_timeout
        )
        candidate_k = max(top_k * 4, 32)
        ranked = await hybrid_search(
            self._search, source_id, runs, normalized_query, vectors[0], candidate_k
        )
        warnings: list[str] = []
        rerank_applied = False
        hits: list[SearchHit] = []
        if self._rerank is not None and ranked:
            try:
                pairs = await asyncio.to_thread(
                    self._rerank.rerank,
                    normalized_query,
                    [chunk.content for chunk, _ in ranked],
                    top_k,
                )
                hits = [
                    _to_hit(ranked[index][0], ranked[index][1], runs, rerank_score=score)
                    for index, score in sorted(pairs, key=lambda pair: pair[1], reverse=True)
                    if 0 <= index < len(ranked)
                ][:top_k]
                rerank_applied = bool(hits)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"rerank failed, hybrid ranking used: {exc}"[:200])
        if not hits:
            hits = [_to_hit(chunk, score, runs) for chunk, score in ranked[:top_k]]
        return SearchResponse(
            hits=hits,
            meta=SearchMeta(
                indexes_searched=list(runs),
                top_k=top_k,
                candidate_k=candidate_k,
                rerank_applied=rerank_applied,
                warnings=warnings,
                latency_ms=round((time.monotonic() - started) * 1000, 1),
            ),
        )

    async def search_ticket_logs(
        self, source_id: int, ticket_id: int, query: str, top_k: int = 8
    ) -> SearchResponse:
        started = time.monotonic()
        normalized_query = query.strip()
        if not normalized_query:
            raise SearchUnavailableError("search query must not be empty")
        if self._ticket_log_search is None:
            raise SearchUnavailableError("ticket log search is unavailable")
        if await self._sources.get_any(source_id) is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        credentials, provider_model_id, embedding_model_id = await self._embedding_target(source_id)
        vectors = await asyncio.to_thread(
            self._embed,
            credentials,
            provider_model_id,
            [normalized_query],
            self._request_timeout,
        )
        candidate_k = max(top_k * 4, 32)
        dense = await self._ticket_log_search.search_dense(
            source_id, ticket_id, embedding_model_id, vectors[0], candidate_k
        )
        lexical = await self._ticket_log_search.search_lexical(
            source_id, ticket_id, normalized_query, candidate_k
        )
        ranked_chunks = rank_with_rrf(
            [_as_retrieved_chunk(item) for item in dense],
            [_as_retrieved_chunk(item) for item in lexical],
        )
        logs_by_id = {item.chunk_id: item for item in [*dense, *lexical]}
        ranked = [(logs_by_id[chunk.chunk_id], score) for chunk, score in ranked_chunks]
        warnings: list[str] = []
        hits: list[SearchHit] = []
        rerank_applied = False
        if self._rerank is not None and ranked:
            try:
                pairs = await asyncio.to_thread(
                    self._rerank.rerank,
                    normalized_query,
                    [chunk.content for chunk, _ in ranked],
                    top_k,
                )
                hits = [
                    _to_ticket_log_hit(ranked[index][0], ranked[index][1], score)
                    for index, score in sorted(pairs, key=lambda pair: pair[1], reverse=True)
                    if 0 <= index < len(ranked)
                ][:top_k]
                rerank_applied = bool(hits)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"rerank failed, hybrid ranking used: {exc}"[:200])
        if not hits:
            hits = [_to_ticket_log_hit(chunk, score) for chunk, score in ranked[:top_k]]
        return SearchResponse(
            hits=hits,
            meta=SearchMeta(
                indexes_searched=["ticket-log"],
                top_k=top_k,
                candidate_k=candidate_k,
                rerank_applied=rerank_applied,
                warnings=warnings,
                latency_ms=round((time.monotonic() - started) * 1000, 1),
            ),
        )

    async def search_ticket_context(
        self, source_id: int, ticket_id: int, query: str, top_k: int = 8
    ) -> SearchResponse:
        started = time.monotonic()
        normalized_query = query.strip()
        if not normalized_query:
            raise SearchUnavailableError("search query must not be empty")
        if await self._sources.get_any(source_id) is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        if self._ticket_log_search is None:
            return await self.search(source_id, normalized_query, top_k=top_k)
        try:
            runs = await self._active_runs(source_id, None)
        except SearchUnavailableError:
            runs = {}
        credentials, provider_model_id, embedding_model_id = await self._embedding_target(source_id)
        vectors = await asyncio.to_thread(
            self._embed,
            credentials,
            provider_model_id,
            [normalized_query],
            self._request_timeout,
        )
        candidate_k = max(top_k * 4, 32)
        dense: list[RetrievedChunk] = []
        lexical: list[RetrievedChunk] = []
        for index_type, run_id in runs.items():
            dense.extend(
                await self._search.search_dense(
                    source_id, index_type, run_id, vectors[0], candidate_k
                )
            )
            lexical.extend(
                await self._search.search_lexical(
                    source_id, index_type, run_id, normalized_query, candidate_k
                )
            )
        dense_logs = await self._ticket_log_search.search_dense(
            source_id, ticket_id, embedding_model_id, vectors[0], candidate_k
        )
        lexical_logs = await self._ticket_log_search.search_lexical(
            source_id, ticket_id, normalized_query, candidate_k
        )
        dense.extend(_as_retrieved_chunk(item) for item in dense_logs)
        lexical.extend(_as_retrieved_chunk(item) for item in lexical_logs)
        log_chunks = {item.chunk_id: item for item in [*dense_logs, *lexical_logs]}
        fused = rank_with_rrf(dense, lexical)
        project_ranked = [item for item in fused if item[0].index_type != "ticket-log"]
        log_ranked = [item for item in fused if item[0].index_type == "ticket-log"]
        ranked: list[tuple[RetrievedChunk, float]] = []
        for position in range(max(len(project_ranked), len(log_ranked))):
            if position < len(project_ranked):
                ranked.append(project_ranked[position])
            if position < len(log_ranked):
                ranked.append(log_ranked[position])
        warnings: list[str] = []
        rerank_applied = False
        hits: list[SearchHit] = []

        def to_hit(chunk: RetrievedChunk, score: float, rerank: float | None = None) -> SearchHit:
            if chunk.index_type == "ticket-log":
                return _to_ticket_log_hit(log_chunks[chunk.chunk_id], score, rerank)
            return _to_hit(chunk, score, runs, rerank)

        if self._rerank is not None and ranked:
            try:
                pairs = await asyncio.to_thread(
                    self._rerank.rerank,
                    normalized_query,
                    [chunk.content for chunk, _ in ranked],
                    top_k,
                )
                hits = [
                    to_hit(ranked[index][0], ranked[index][1], score)
                    for index, score in sorted(pairs, key=lambda pair: pair[1], reverse=True)
                    if 0 <= index < len(ranked)
                ][:top_k]
                rerank_applied = bool(hits)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"rerank failed, hybrid ranking used: {exc}"[:200])
        if not hits:
            hits = [to_hit(chunk, score) for chunk, score in ranked[:top_k]]
        indexes_searched = [*runs]
        if self._ticket_log_search is not None:
            indexes_searched.append("ticket-log")
        return SearchResponse(
            hits=hits,
            meta=SearchMeta(
                indexes_searched=indexes_searched,
                top_k=top_k,
                candidate_k=candidate_k,
                rerank_applied=rerank_applied,
                warnings=warnings,
                latency_ms=round((time.monotonic() - started) * 1000, 1),
            ),
        )

    async def _active_runs(
        self, source_id: int, index_types: Sequence[str] | None
    ) -> dict[str, int]:
        statuses = await self._indexes.statuses(source_id)
        completed = {
            status.index_type: status.run_id
            for status in statuses
            if status.status == "completed" and status.run_id is not None
        }
        requested = list(index_types) if index_types else list(completed)
        runs = {
            index_type: completed[index_type] for index_type in requested if index_type in completed
        }
        if not runs:
            unknown = [item for item in requested if item not in completed]
            detail = (
                f"; unknown or not completed index types: {', '.join(unknown)}" if unknown else ""
            )
            raise SearchUnavailableError(f"no completed indexes to search{detail}")
        return runs

    async def _embedding_target(self, source_id: int) -> tuple[ProviderCredentials, str, int]:
        selections = await self._models.get_project_selections(source_id)
        model_id = selections.get("indexing")
        if model_id is None:
            raise SearchUnavailableError("select an embedding model before searching")
        model = await self._models.get_model(model_id)
        if model is None or "embedding" not in model.capabilities:
            raise SearchUnavailableError("the selected embedding model is unavailable")
        if model.status not in {"available", "installed"}:
            raise SearchUnavailableError("the selected embedding model is not ready")
        credentials = await self._models.get_credentials(model.provider_connection_id)
        if credentials is None:
            raise SearchUnavailableError("the embedding model provider is unavailable")
        return credentials, model.provider_model_id, model_id


def _to_hit(
    chunk: RetrievedChunk,
    score: float,
    runs: Mapping[str, int],
    rerank_score: float | None = None,
) -> SearchHit:
    return SearchHit(
        index_type=chunk.index_type,
        run_id=runs.get(chunk.index_type, 0),
        path=chunk.path,
        branch=chunk.branch,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        symbol=chunk.symbol,
        content=chunk.content,
        score=score,
        rerank_score=rerank_score,
    )


def _as_retrieved_chunk(chunk: RetrievedTicketLogChunk) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        index_type="ticket-log",
        path=chunk.path,
        branch="",
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        symbol=None,
        content=chunk.content,
        metadata=chunk.metadata,
        score=chunk.score,
    )


def _to_ticket_log_hit(
    chunk: RetrievedTicketLogChunk, score: float, rerank_score: float | None = None
) -> SearchHit:
    return SearchHit(
        index_type="ticket-log",
        run_id=0,
        path=chunk.path,
        branch="",
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        symbol=None,
        content=chunk.content,
        score=score,
        rerank_score=rerank_score,
        ticket_id=chunk.ticket_id,
        attachment_id=chunk.attachment_id,
        event_timestamp=chunk.event_timestamp,
    )
