from dataclasses import dataclass
from typing import Any, Protocol

from app.domain.model_provider_entities import ProviderCredentials


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: int
    index_type: str
    path: str
    branch: str
    start_line: int | None
    end_line: int | None
    symbol: str | None
    content: str
    metadata: dict[str, Any]
    score: float


class IndexSearchRepository(Protocol):
    async def search_dense(
        self, source_id: int, index_type: str, run_id: int, vector: list[float], limit: int
    ) -> list[RetrievedChunk]: ...

    async def search_lexical(
        self, source_id: int, index_type: str, run_id: int, query: str, limit: int
    ) -> list[RetrievedChunk]: ...


class MaterialGenerationGateway(Protocol):
    def embed_queries(
        self,
        credentials: ProviderCredentials,
        model_id: str,
        queries: list[str],
        timeout: int,
    ) -> list[list[float]]: ...

    def generate_json(
        self,
        credentials: ProviderCredentials,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        timeout: int,
        max_output_tokens: int,
    ) -> str: ...
