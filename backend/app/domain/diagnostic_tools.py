from dataclasses import dataclass
from typing import Protocol

from app.domain.repositories.retrieval import SearchHit


@dataclass(frozen=True, slots=True)
class DiagnosticEvidence:
    status: str
    hits: list[SearchHit]
    reason: str


class DiagnosticTools(Protocol):
    async def observe_ui(self, source_id: int, ticket_id: int) -> DiagnosticEvidence: ...

    async def search_web(self, source_id: int, ticket_id: int) -> DiagnosticEvidence: ...
