import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tickets import Ticket, TicketStep


class TicketSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, source_id: int, title: str, description: str) -> Ticket:
        result = await self._session.execute(
            text(
                "INSERT INTO tickets (source_id, title, description) "
                "VALUES (:source_id, :title, :description) RETURNING id"
            ),
            {"source_id": source_id, "title": title, "description": description},
        )
        ticket_id = int(result.scalar_one())
        await self._session.commit()
        ticket = await self.get(ticket_id)
        assert ticket is not None
        return ticket

    async def get(self, ticket_id: int) -> Ticket | None:
        rows = await self._session.execute(
            text(_TICKET_COLUMNS + " WHERE ticket.id = :ticket_id"),
            {"ticket_id": ticket_id},
        )
        row = rows.one_or_none()
        return _to_ticket(row) if row is not None else None

    async def list_for_source(self, source_id: int) -> list[Ticket]:
        rows = await self._session.execute(
            text(_TICKET_COLUMNS + " WHERE ticket.source_id = :source_id ORDER BY ticket.id DESC"),
            {"source_id": source_id},
        )
        return [_to_ticket(row) for row in rows.all()]

    async def update_result(
        self,
        ticket_id: int,
        status: str,
        triage: dict[str, Any] | None = None,
        answer: str | None = None,
        escalate_reason: str | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> Ticket | None:
        await self._session.execute(
            text(
                "UPDATE tickets SET status = :status, "
                "triage_json = COALESCE(CAST(:triage AS jsonb), triage_json), "
                "answer = :answer, escalate_reason = :escalate_reason, "
                "citations_json = CAST(:citations AS jsonb), updated_at = now() "
                "WHERE id = :ticket_id"
            ),
            {
                "ticket_id": ticket_id,
                "status": status,
                "triage": json.dumps(triage, ensure_ascii=False) if triage is not None else None,
                "answer": answer,
                "escalate_reason": escalate_reason,
                "citations": json.dumps(citations, ensure_ascii=False) if citations is not None else None,
            },
        )
        await self._session.commit()
        return await self.get(ticket_id)

    async def add_step(
        self,
        ticket_id: int,
        step: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        model_id: int | None,
        duration_ms: int,
    ) -> TicketStep:
        result = await self._session.execute(
            text(
                "INSERT INTO ticket_steps (ticket_id, step, input_json, output_json, model_id, duration_ms) "
                "VALUES (:ticket_id, :step, CAST(:input_json AS jsonb), CAST(:output_json AS jsonb), "
                ":model_id, :duration_ms) RETURNING id, created_at"
            ),
            {
                "ticket_id": ticket_id,
                "step": step,
                "input_json": json.dumps(input_data, ensure_ascii=False),
                "output_json": json.dumps(output_data, ensure_ascii=False),
                "model_id": model_id,
                "duration_ms": duration_ms,
            },
        )
        row = result.one()
        await self._session.commit()
        return TicketStep(
            id=int(row.id),
            ticket_id=ticket_id,
            step=step,
            input_data=input_data,
            output_data=output_data,
            model_id=model_id,
            duration_ms=duration_ms,
            created_at=row.created_at,
        )

    async def list_steps(self, ticket_id: int) -> list[TicketStep]:
        rows = await self._session.execute(
            text(
                "SELECT id, ticket_id, step, input_json, output_json, model_id, duration_ms, created_at "
                "FROM ticket_steps WHERE ticket_id = :ticket_id ORDER BY id"
            ),
            {"ticket_id": ticket_id},
        )
        return [_to_step(row) for row in rows.all()]


_TICKET_COLUMNS = (
    "SELECT ticket.id, ticket.source_id, ticket.title, ticket.description, ticket.status, "
    "ticket.triage_json, ticket.answer, ticket.escalate_reason, ticket.citations_json, "
    "ticket.created_at, ticket.updated_at FROM tickets AS ticket"
)


def _to_ticket(row: Any) -> Ticket:
    return Ticket(
        id=int(row.id),
        source_id=int(row.source_id),
        title=str(row.title),
        description=str(row.description),
        status=str(row.status),
        triage=row.triage_json if isinstance(row.triage_json, dict) else None,
        answer=row.answer,
        escalate_reason=row.escalate_reason,
        citations=row.citations_json if isinstance(row.citations_json, list) else None,
        created_at=row.created_at if isinstance(row.created_at, datetime) else None,
        updated_at=row.updated_at if isinstance(row.updated_at, datetime) else None,
    )


def _to_step(row: Any) -> TicketStep:
    return TicketStep(
        id=int(row.id),
        ticket_id=int(row.ticket_id),
        step=str(row.step),
        input_data=row.input_json if isinstance(row.input_json, dict) else {},
        output_data=row.output_json if isinstance(row.output_json, dict) else {},
        model_id=int(row.model_id) if row.model_id is not None else None,
        duration_ms=int(row.duration_ms),
        created_at=row.created_at if isinstance(row.created_at, datetime) else None,
    )
