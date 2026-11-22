from typing import Any

import pytest

from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import ProviderCredentials, WorkspaceModelEntry
from app.domain.repositories.indexing import IndexRunStatus
from app.domain.repositories.material_generation import RetrievedChunk
from app.domain.repositories.retrieval import (
    RerankGateway,
    SearchUnavailableError,
)
from app.domain.repositories.ticket_log_search import RetrievedTicketLogChunk
from app.usecase.retrieval import RetrievalUsecase, rank_with_rrf


def test_rrf_ranks_each_modality_across_indexes_before_fusion() -> None:
    code = _chunk(1, "code", "a.cpp", "unrelated", 0.1)
    doc = _chunk(2, "documentation", "guide.md", "exact match", 0.9)
    assert rank_with_rrf([code, doc], [code, doc])[0][0] == doc


class FakeSources:
    def __init__(self, exists: bool = True) -> None:
        self.exists = exists

    async def get_any(self, source_id: int) -> dict[str, Any] | None:
        return {"id": source_id, "name": "repo"} if self.exists else None


class FakeIndexing:
    def __init__(self, statuses: list[IndexRunStatus]) -> None:
        self._items = statuses

    async def statuses(self, source_id: int) -> list[IndexRunStatus]:
        return self._items


def _run_status(index_type: str, status: str, run_id: int | None) -> IndexRunStatus:
    return IndexRunStatus(
        index_type=index_type,
        status=status,
        progress=100 if status == "completed" else 0,
        run_id=run_id,
        snapshot_id=run_id,
        files_total=1,
        chunks_total=1,
        error=None,
        updated_at=None,
    )


def _chunk(chunk_id: int, index_type: str, path: str, content: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        index_type=index_type,
        path=path,
        branch="",
        start_line=None,
        end_line=None,
        symbol=None,
        content=content,
        metadata={},
        score=score,
    )


class FakeSearch:
    def __init__(self) -> None:
        self.dense_calls: list[tuple[str, int]] = []
        self.lexical_calls: list[tuple[str, int]] = []

    async def search_dense(
        self, source_id: int, index_type: str, run_id: int, vector: list[float], limit: int
    ) -> list[RetrievedChunk]:
        self.dense_calls.append((index_type, limit))
        rows = {
            "code": [
                _chunk(1, "code", "code_a.py", "dense code", 0.9),
                _chunk(2, "code", "code_b.py", "dense code b", 0.8),
            ],
            "documentation": [_chunk(5, "documentation", "docs.md", "dense docs", 0.7)],
        }
        return rows.get(index_type, [])

    async def search_lexical(
        self, source_id: int, index_type: str, run_id: int, query: str, limit: int
    ) -> list[RetrievedChunk]:
        self.lexical_calls.append((index_type, limit))
        rows = {
            "code": [
                _chunk(2, "code", "code_b.py", "lexical code b", 0.5),
                _chunk(3, "code", "code_c.py", "lexical code c", 0.4),
            ],
            "documentation": [_chunk(6, "documentation", "flows.json", "lexical flow", 0.3)],
        }
        return rows.get(index_type, [])


class FakeTicketLogSearch:
    async def search_dense(
        self,
        source_id: int,
        ticket_id: int,
        embedding_model_id: int,
        vector: list[float],
        limit: int,
    ) -> list[RetrievedTicketLogChunk]:
        return [
            RetrievedTicketLogChunk(
                chunk_id=11,
                attachment_id=4,
                ticket_id=ticket_id,
                path="logs/server.log",
                start_line=12,
                end_line=18,
                event_timestamp="2026-11-17T01:02:03Z",
                content="OOM killer terminated worker",
                metadata={"encoding": "utf-8"},
                score=0.9,
            )
        ]

    async def search_lexical(
        self, source_id: int, ticket_id: int, query: str, limit: int
    ) -> list[RetrievedTicketLogChunk]:
        return []


class FakeModels:
    def __init__(self, selection: int | None = 1) -> None:
        self.selection = selection

    async def get_project_selections(self, source_id: int) -> dict[str, int]:
        return {"indexing": self.selection} if self.selection is not None else {}

    async def get_model(self, model_id: int) -> WorkspaceModelEntry | None:
        if model_id != 1:
            return None
        return WorkspaceModelEntry(
            id=1,
            provider_connection_id=7,
            provider_model_id="bge-m3",
            display_name="bge-m3",
            capabilities=["embedding"],
            status="installed",
        )

    async def get_credentials(self, connection_id: int) -> ProviderCredentials | None:
        return ProviderCredentials(
            id=connection_id,
            provider_type="ollama",
            name="ollama",
            base_url="http://localhost:11434",
            api_key=None,
        )


def fake_embed(
    credentials: ProviderCredentials, model_id: str, queries: list[str], timeout: int
) -> list[list[float]]:
    return [[0.1, 0.2] for _ in queries]


class FailingRerank:
    def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        raise RuntimeError("rerank service down")


class FixedRerank:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        self.calls.append((query, len(documents), top_n))
        return [(1, 0.99), (0, 0.42)]


def _statuses() -> list[IndexRunStatus]:
    return [
        _run_status("code", "completed", 11),
        _run_status("documentation", "completed", 22),
        _run_status("user_flow", "not_started", None),
    ]


def _usecase(
    statuses: list[IndexRunStatus] | None = None,
    exists: bool = True,
    selection: int | None = 1,
    rerank: RerankGateway | None = None,
) -> tuple[RetrievalUsecase, FakeSearch, None]:
    search = FakeSearch()
    usecase = RetrievalUsecase(
        sources=FakeSources(exists),
        indexes=FakeIndexing(statuses if statuses is not None else _statuses()),
        search=search,
        models=FakeModels(selection),
        embed=fake_embed,
        rerank=rerank,
        request_timeout=5,
    )
    return usecase, search, None


async def test_search_fuses_dense_and_lexical_across_completed_indexes() -> None:
    usecase, search, _ = _usecase()
    response = await usecase.search(1, "архив", top_k=5)

    assert search.dense_calls == [("code", 32), ("documentation", 32)]
    paths = [hit.path for hit in response.hits]
    assert "code_b.py" in paths
    assert set(response.meta.indexes_searched) == {"code", "documentation"}
    assert response.meta.rerank_applied is False
    assert response.meta.top_k == 5
    assert response.hits[0].score >= response.hits[-1].score
    assert response.hits[0].source_ref.startswith("run:11:")
    assert response.meta.latency_ms >= 0


async def test_search_restricted_to_requested_index_types() -> None:
    usecase, search, _ = _usecase()
    response = await usecase.search(1, "документация", index_types=["documentation"], top_k=3)
    assert search.dense_calls == [("documentation", 32)]
    assert [hit.path for hit in response.hits] == ["docs.md", "flows.json"]


async def test_search_unknown_project_raises_source_not_found() -> None:
    usecase, _, _ = _usecase(exists=False)
    with pytest.raises(SourceNotFoundError):
        await usecase.search(1, "query")


async def test_ticket_log_search_returns_attachment_scoped_citation() -> None:
    search = FakeSearch()
    usecase = RetrievalUsecase(
        sources=FakeSources(),
        indexes=FakeIndexing([]),
        search=search,
        models=FakeModels(),
        embed=fake_embed,
        rerank=None,
        request_timeout=5,
        ticket_log_search=FakeTicketLogSearch(),
    )

    response = await usecase.search_ticket_logs(1, 71, "OOM kill", top_k=4)

    assert [hit.path for hit in response.hits] == ["logs/server.log"]
    assert response.hits[0].ticket_id == 71
    assert response.hits[0].attachment_id == 4
    assert response.hits[0].event_timestamp == "2026-11-17T01:02:03Z"
    assert response.hits[0].source_ref.startswith("ticket:71:attachment:4:")


async def test_ticket_context_embeds_once_and_combines_project_and_ticket_logs() -> None:
    search = FakeSearch()
    embed_calls: list[list[str]] = []

    def counted_embed(
        credentials: ProviderCredentials, model_id: str, queries: list[str], timeout: int
    ) -> list[list[float]]:
        embed_calls.append(queries)
        return fake_embed(credentials, model_id, queries, timeout)

    usecase = RetrievalUsecase(
        sources=FakeSources(),
        indexes=FakeIndexing(_statuses()),
        search=search,
        models=FakeModels(),
        embed=counted_embed,
        rerank=None,
        request_timeout=5,
        ticket_log_search=FakeTicketLogSearch(),
    )

    response = await usecase.search_ticket_context(1, 71, "OOM kill", top_k=5)

    assert len(embed_calls) == 1
    assert {hit.path for hit in response.hits} >= {"code_a.py", "logs/server.log"}
    assert response.hits[0].source_ref.startswith("run:")
    assert any(hit.source_ref.startswith("ticket:71:attachment:4:") for hit in response.hits)


async def test_search_without_completed_indexes_raises_unavailable() -> None:
    statuses = [_run_status("code", "queued", None)]
    usecase, _, _ = _usecase(statuses=statuses)
    with pytest.raises(SearchUnavailableError):
        await usecase.search(1, "query")


async def test_search_without_embedding_model_raises_unavailable() -> None:
    usecase, _, _ = _usecase(selection=None)
    with pytest.raises(SearchUnavailableError):
        await usecase.search(1, "query")


async def test_rerank_orders_hits_and_reports_applied() -> None:
    rerank = FixedRerank()
    usecase, _, _ = _usecase(rerank=rerank)
    response = await usecase.search(1, "архив", top_k=2)

    assert rerank.calls and rerank.calls[0][1] >= 3
    assert response.meta.rerank_applied is True
    assert next(hit.path for hit in response.hits) in {"code_b.py", "code_a.py"}
    assert all(hit.rerank_score is not None for hit in response.hits)
    assert len(response.hits) <= 2


async def test_rerank_failure_degrades_to_hybrid_results() -> None:
    usecase, _, _ = _usecase(rerank=FailingRerank())
    response = await usecase.search(1, "архив")

    assert response.meta.rerank_applied is False
    assert response.hits
    assert response.meta.warnings


async def test_search_rejects_empty_query() -> None:
    usecase, _, _ = _usecase()
    with pytest.raises(SearchUnavailableError):
        await usecase.search(1, "   ")
