from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter.config import get_settings
from app.adapter.db import get_session
from app.adapter.material_generation import MaterialGenerationAdapter
from app.adapter.repositories import (
    ModelProviderSqlRepository,
    SourceSqlRepository,
    TicketSqlRepository,
)
from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import ProviderUnavailableError
from app.domain.tickets import Ticket, TicketConflictError, TicketNotFoundError, TicketStep
from app.handler.routes.search import build_retrieval_usecase
from app.handler.schemas import (
    TicketBriefOut,
    TicketCitationOut,
    TicketCreateIn,
    TicketDetailOut,
    TicketOut,
    TicketStatsOut,
    TicketStepOut,
)
from app.usecase.ticket_agent import (
    TicketAgentConfig,
    TicketAgentResponseError,
    TicketAgentUnavailableError,
    TicketAgentUsecase,
)

router = APIRouter(tags=["tickets"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def build_ticket_usecase(session: AsyncSession) -> TicketAgentUsecase:
    settings = get_settings()
    return TicketAgentUsecase(
        tickets=TicketSqlRepository(session),
        sources=SourceSqlRepository(session),
        models=ModelProviderSqlRepository(session, settings.model_secrets_key),
        retrieval=build_retrieval_usecase(session),
        gateway=MaterialGenerationAdapter(),
        config=TicketAgentConfig(
            timeout_seconds=settings.ticket_agent_timeout_seconds,
            max_output_tokens=settings.ticket_agent_max_output_tokens,
            context_chunks=settings.ticket_context_chunks,
            max_context_characters=settings.ticket_max_context_characters,
        ),
    )


@router.post("/sources/{source_id}/tickets", status_code=201, response_model=TicketBriefOut)
async def create_ticket(
    source_id: int, payload: TicketCreateIn, session: SessionDep
) -> TicketBriefOut:
    try:
        ticket = await build_ticket_usecase(session).create_ticket(
            source_id, payload.title, payload.description
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return _brief_out(ticket)


@router.get("/sources/{source_id}/tickets", response_model=list[TicketBriefOut])
async def list_tickets(source_id: int, session: SessionDep) -> list[TicketBriefOut]:
    try:
        tickets = await build_ticket_usecase(session).list_tickets(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return [_brief_out(ticket) for ticket in tickets]


@router.get("/sources/{source_id}/tickets/stats", response_model=TicketStatsOut)
async def ticket_stats(source_id: int, session: SessionDep) -> TicketStatsOut:
    try:
        stats = await build_ticket_usecase(session).ticket_stats(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return TicketStatsOut(
        total=stats.total,
        by_status=stats.by_status,
        completed=stats.completed,
        autoresolve_rate=stats.autoresolve_rate,
        tokens_in=stats.tokens_in,
        tokens_out=stats.tokens_out,
        cost_usd=stats.cost_usd,
        avg_cost_usd=stats.avg_cost_usd,
        avg_tokens_per_ticket=stats.avg_tokens_per_ticket,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketDetailOut)
async def ticket_details(ticket_id: int, session: SessionDep) -> TicketDetailOut:
    try:
        ticket, steps = await build_ticket_usecase(session).ticket_details(ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Ticket not found") from exc
    return TicketDetailOut(ticket=_ticket_out(ticket), steps=[_step_out(s) for s in steps])


@router.post("/tickets/{ticket_id}/run", response_model=TicketDetailOut)
async def run_ticket(ticket_id: int, session: SessionDep) -> TicketDetailOut:
    usecase = build_ticket_usecase(session)
    try:
        ticket = await usecase.run(ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Ticket not found") from exc
    except TicketConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TicketAgentUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (TicketAgentResponseError, ProviderUnavailableError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _, steps = await usecase.ticket_details(ticket.id)
    return TicketDetailOut(ticket=_ticket_out(ticket), steps=[_step_out(s) for s in steps])


def _brief_out(ticket: Ticket) -> TicketBriefOut:
    return TicketBriefOut(
        id=ticket.id,
        title=ticket.title,
        status=ticket.status,
        created_at=_iso(ticket.created_at),
    )


def _ticket_out(ticket: Ticket) -> TicketOut:
    return TicketOut(
        id=ticket.id,
        source_id=ticket.source_id,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        triage=ticket.triage,
        answer=ticket.answer,
        escalate_reason=ticket.escalate_reason,
        citations=[TicketCitationOut.model_validate(item) for item in ticket.citations or []],
        created_at=_iso(ticket.created_at),
        updated_at=_iso(ticket.updated_at),
    )


def _step_out(step: TicketStep) -> TicketStepOut:
    return TicketStepOut(
        step=step.step,
        input_data=step.input_data,
        output_data=step.output_data,
        model_id=step.model_id,
        duration_ms=step.duration_ms,
        tokens_in=step.tokens_in,
        tokens_out=step.tokens_out,
        cost_usd=step.cost_usd,
        created_at=_iso(step.created_at),
    )


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None
