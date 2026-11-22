from typing import Annotated

from botocore.exceptions import BotoCoreError
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter.config import get_settings
from app.adapter.db import get_session
from app.adapter.material_generation import MaterialGenerationAdapter
from app.adapter.repositories import (
    ModelProviderSqlRepository,
    SourceSqlRepository,
    TicketSqlRepository,
)
from app.adapter.repositories.solver import SolverSqlRepository
from app.adapter.repositories.ticket_logs import TicketLogSqlRepository
from app.adapter.ticket_log_storage import build_ticket_log_storage
from app.adapter.ticket_log_tasks import run_ticket_log_attachment
from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import ProviderUnavailableError
from app.domain.solver import SolverProfileNotFoundError
from app.domain.ticket_logs import TicketLogAttachment
from app.domain.tickets import Ticket, TicketConflictError, TicketNotFoundError, TicketStep
from app.handler.routes.search import build_retrieval_usecase
from app.handler.schemas import (
    TicketBriefOut,
    TicketCitationOut,
    TicketCreateIn,
    TicketDetailOut,
    TicketLogAttachmentOut,
    TicketOut,
    TicketRunIn,
    TicketStatsOut,
    TicketStepOut,
)
from app.usecase.ticket_agent import (
    TicketAgentConfig,
    TicketAgentResponseError,
    TicketAgentUnavailableError,
    TicketAgentUsecase,
)
from app.usecase.ticket_log_uploads import TicketLogUploadError, validate_log_archive_upload

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
    usecase = build_ticket_usecase(session)
    try:
        ticket, steps = await usecase.ticket_details(ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Ticket not found") from exc
    return TicketDetailOut(
        ticket=_ticket_out(ticket),
        steps=[_step_out(s) for s in steps],
        runs=await usecase.ticket_runs(ticket_id),
    )


@router.post(
    "/tickets/{ticket_id}/log-attachments",
    status_code=201,
    response_model=TicketLogAttachmentOut,
)
async def upload_ticket_log_attachment(
    ticket_id: int, session: SessionDep, file: Annotated[UploadFile, File()]
) -> TicketLogAttachmentOut:
    ticket = await TicketSqlRepository(session).get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    settings = get_settings()
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="archive upload is too large")
        chunks.append(chunk)
    try:
        filename, size_bytes = validate_log_archive_upload(
            file.filename or "", b"".join(chunks), settings.max_upload_bytes
        )
    except TicketLogUploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    storage = build_ticket_log_storage(settings)
    storage_key = storage.store(ticket.source_id, ticket.id, filename, b"".join(chunks))
    repository = TicketLogSqlRepository(session)
    try:
        attachment = await repository.create_attachment(
            ticket.source_id, ticket.id, filename, storage_key, size_bytes
        )
    except SQLAlchemyError as exc:
        storage.delete(storage_key)
        raise HTTPException(
            status_code=503, detail="Could not save log archive attachment"
        ) from exc
    try:
        run_ticket_log_attachment.delay(attachment.id)
    except Exception as exc:
        await repository.update_status(
            attachment.id, "failed", "Не удалось поставить архив в очередь"
        )
        raise HTTPException(
            status_code=503, detail="Log archive processing queue is unavailable"
        ) from exc
    return _log_attachment_out(attachment)


@router.get(
    "/tickets/{ticket_id}/log-attachments",
    response_model=list[TicketLogAttachmentOut],
)
async def list_ticket_log_attachments(
    ticket_id: int, session: SessionDep
) -> list[TicketLogAttachmentOut]:
    ticket = await TicketSqlRepository(session).get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    attachments = await TicketLogSqlRepository(session).list_attachments(
        ticket.source_id, ticket.id
    )
    return [_log_attachment_out(item) for item in attachments]


@router.post(
    "/tickets/{ticket_id}/log-attachments/{attachment_id}/retry",
    status_code=202,
    response_model=TicketLogAttachmentOut,
)
async def retry_ticket_log_attachment(
    ticket_id: int, attachment_id: int, session: SessionDep
) -> TicketLogAttachmentOut:
    ticket = await TicketSqlRepository(session).get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    repository = TicketLogSqlRepository(session)
    attachment = await repository.get_attachment(ticket.source_id, ticket.id, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Log archive attachment not found")
    if attachment.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed log archives can be retried")
    updated = await repository.update_status(attachment.id, "queued", None)
    if updated is None:
        raise HTTPException(status_code=404, detail="Log archive attachment not found")
    try:
        run_ticket_log_attachment.delay(attachment.id)
    except Exception as exc:
        await repository.update_status(
            attachment.id, "failed", "Не удалось поставить архив в очередь"
        )
        raise HTTPException(
            status_code=503, detail="Log archive processing queue is unavailable"
        ) from exc
    return _log_attachment_out(updated)


@router.delete("/tickets/{ticket_id}/log-attachments/{attachment_id}", status_code=204)
async def delete_ticket_log_attachment(
    ticket_id: int, attachment_id: int, session: SessionDep
) -> Response:
    ticket = await TicketSqlRepository(session).get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    repository = TicketLogSqlRepository(session)
    attachment = await repository.get_attachment(ticket.source_id, ticket.id, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Log archive attachment not found")
    try:
        build_ticket_log_storage(get_settings()).delete(attachment.storage_key)
    except BotoCoreError as exc:
        raise HTTPException(status_code=503, detail="Could not delete log archive") from exc
    storage_key = await repository.delete_attachment(ticket.source_id, ticket.id, attachment_id)
    if storage_key is None:
        raise HTTPException(status_code=404, detail="Log archive attachment not found")
    return Response(status_code=204)


@router.post("/tickets/{ticket_id}/run", response_model=TicketDetailOut)
async def run_ticket(
    ticket_id: int, session: SessionDep, payload: TicketRunIn | None = None
) -> TicketDetailOut:
    ticket = await TicketSqlRepository(session).get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    attachments = await TicketLogSqlRepository(session).list_attachments(
        ticket.source_id, ticket.id
    )
    if any(item.status != "ready" for item in attachments):
        raise HTTPException(
            status_code=409,
            detail="Retry or remove failed log archives and wait for processing attachments before running the issue",
        )
    usecase = build_ticket_usecase(session)
    try:
        profile = await SolverSqlRepository(session).get(
            ticket.source_id, payload.profile_id if payload is not None else None
        )
        ticket = await usecase.run(ticket_id, profile=profile)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Ticket not found") from exc
    except (SolverProfileNotFoundError, SourceNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TicketConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TicketAgentUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (TicketAgentResponseError, ProviderUnavailableError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _, steps = await usecase.ticket_details(ticket.id)
    return TicketDetailOut(
        ticket=_ticket_out(ticket),
        steps=[_step_out(s) for s in steps],
        runs=await usecase.ticket_runs(ticket.id),
    )


def _brief_out(ticket: Ticket) -> TicketBriefOut:
    return TicketBriefOut(
        id=ticket.id,
        title=ticket.title,
        status=ticket.status,
        created_at=_iso(ticket.created_at),
        has_unready_log_attachments=ticket.has_unready_log_attachments,
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
        run_id=step.run_id,
        status=step.status,
    )


def _log_attachment_out(attachment: TicketLogAttachment) -> TicketLogAttachmentOut:
    return TicketLogAttachmentOut(
        id=attachment.id,
        filename=attachment.filename,
        size_bytes=attachment.size_bytes,
        status=attachment.status,
        error=attachment.error,
        created_at=_iso(attachment.created_at),
        updated_at=_iso(attachment.updated_at),
    )


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None
