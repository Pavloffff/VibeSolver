from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class RetrievedTicketLogChunk:
    chunk_id: int
    attachment_id: int
    ticket_id: int
    path: str
    start_line: int
    end_line: int
    event_timestamp: str | None
    content: str
    metadata: dict[str, Any]
    score: float


class TicketLogSearchRepository(Protocol):
    async def search_dense(
        self,
        source_id: int,
        ticket_id: int,
        embedding_model_id: int,
        vector: list[float],
        limit: int,
    ) -> list[RetrievedTicketLogChunk]: ...

    async def search_lexical(
        self, source_id: int, ticket_id: int, query: str, limit: int
    ) -> list[RetrievedTicketLogChunk]: ...
