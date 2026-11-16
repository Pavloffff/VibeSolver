from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.domain.model_provider_entities import ProviderCredentials


@dataclass(frozen=True, slots=True)
class SearchHit:
    index_type: str
    run_id: int
    path: str
    branch: str
    start_line: int | None
    end_line: int | None
    symbol: str | None
    content: str
    score: float
    rerank_score: float | None = None

    @property
    def source_ref(self) -> str:
        return f"run:{self.run_id}:{self.path}:{self.start_line if self.start_line is not None else 0}"


@dataclass(frozen=True, slots=True)
class SearchMeta:
    indexes_searched: list[str]
    top_k: int
    candidate_k: int
    rerank_applied: bool
    warnings: list[str]
    latency_ms: float


@dataclass(frozen=True, slots=True)
class SearchResponse:
    hits: list[SearchHit]
    meta: SearchMeta


class SearchUnavailableError(RuntimeError):
    pass


class RerankGateway(Protocol):
    def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]: ...


EmbedQueries = Callable[[ProviderCredentials, str, list[str], int], list[list[float]]]
