from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter.config import get_settings
from app.adapter.db import get_session
from app.adapter.material_generation import MaterialGenerationAdapter
from app.adapter.repositories.model_providers import ModelProviderSqlRepository
from app.adapter.repositories.ticket_localization import TicketLocalizationSqlRepository
from app.domain.tickets import TicketNotFoundError, TicketResultTranslations
from app.usecase.ticket_localization import TicketLocalizationUsecase

router = APIRouter(tags=["tickets"])


@router.post("/tickets/{ticket_id}/localize", response_model=TicketResultTranslations)
async def localize_ticket(
    ticket_id: int, session: Annotated[AsyncSession, Depends(get_session)]
) -> TicketResultTranslations:
    settings = get_settings()
    usecase = TicketLocalizationUsecase(
        TicketLocalizationSqlRepository(session),
        ModelProviderSqlRepository(session, settings.model_secrets_key),
        MaterialGenerationAdapter(),
        settings.ticket_agent_timeout_seconds,
        settings.ticket_agent_max_output_tokens,
    )
    try:
        async with session.begin():
            return await usecase.localize(ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Ticket not found") from exc
