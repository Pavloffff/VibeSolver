from typing import Any, Protocol

from app.domain.tickets import Ticket, TicketStep


class TicketRepository(Protocol):
    async def create(self, source_id: int, title: str, description: str) -> Ticket: ...

    async def get(self, ticket_id: int) -> Ticket | None: ...

    async def list_for_source(self, source_id: int) -> list[Ticket]: ...

    async def update_result(
        self,
        ticket_id: int,
        status: str,
        triage: dict[str, Any] | None = None,
        answer: str | None = None,
        escalate_reason: str | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> Ticket | None: ...

    async def add_step(
        self,
        ticket_id: int,
        step: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        model_id: int | None,
        duration_ms: int,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
    ) -> TicketStep: ...

    async def list_steps(self, ticket_id: int) -> list[TicketStep]: ...

    async def usage_rows(self, source_id: int) -> list[tuple[str, int | None, int | None, float | None]]: ...
