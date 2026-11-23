from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter.config import Settings, get_settings
from app.adapter.db import get_session
from app.adapter.repositories.diagnostic_options import DiagnosticOptionsRepository
from app.domain.entities import SourceNotFoundError
from app.domain.tickets import TicketNotFoundError
from app.domain.ui_observation import UiObservation

router = APIRouter(tags=["solver"])


def repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DiagnosticOptionsRepository:
    return DiagnosticOptionsRepository(session)


Repo = Annotated[DiagnosticOptionsRepository, Depends(repository)]
Config = Annotated[Settings, Depends(get_settings)]


class ProjectTools(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ui_probe: str | None = Field(default=None, max_length=150)
    web_provider: str | None = Field(default=None, max_length=150)
    allow_web_search: StrictBool = False


class ProjectToolsOut(ProjectTools):
    available_ui_probes: list[str]
    available_web_providers: list[str]


class WebConsent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    use_web_search: bool


class ObservationOut(BaseModel):
    observation: UiObservation | None


@contextmanager
def known_resource() -> Iterator[None]:
    try:
        yield
    except (SourceNotFoundError, TicketNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc


def tool_choices(
    ui: str | None, web: str | None, allow_web_search: bool, settings: Settings
) -> ProjectToolsOut:
    return ProjectToolsOut(
        ui_probe=ui,
        web_provider=web,
        allow_web_search=allow_web_search,
        available_ui_probes=sorted(settings.diagnostic_ui_probes),
        available_web_providers=sorted(settings.diagnostic_web_providers),
    )


@router.get("/sources/{source_id}/diagnostic-tools")
async def project_tools(source_id: int, repo: Repo, settings: Config) -> ProjectToolsOut:
    with known_resource():
        ui, web, allow_web_search = await repo.project(source_id)
    return tool_choices(ui, web, allow_web_search, settings)


@router.put("/sources/{source_id}/diagnostic-tools")
async def set_project_tools(
    source_id: int, payload: ProjectTools, repo: Repo, settings: Config
) -> ProjectToolsOut:
    if payload.ui_probe is not None and payload.ui_probe not in settings.diagnostic_ui_probes:
        raise HTTPException(422, "Select an observation configured on this server")
    if (
        payload.web_provider is not None
        and payload.web_provider not in settings.diagnostic_web_providers
    ):
        raise HTTPException(422, "Select a search provider configured on this server")
    if payload.allow_web_search and payload.web_provider is None:
        raise HTTPException(422, "Select a search provider before enabling web search")
    with known_resource():
        await repo.save_project(
            source_id, payload.ui_probe, payload.web_provider, payload.allow_web_search
        )
    return tool_choices(payload.ui_probe, payload.web_provider, payload.allow_web_search, settings)


@router.get("/tickets/{ticket_id}/diagnostic-options")
async def ticket_options(ticket_id: int, repo: Repo) -> WebConsent:
    with known_resource():
        ticket = await repo.ticket(await repo.ticket_source(ticket_id), ticket_id)
        if ticket is None:
            raise TicketNotFoundError("Ticket not found")
    return WebConsent(use_web_search=ticket[0])


@router.put("/tickets/{ticket_id}/diagnostic-options")
async def set_ticket_options(ticket_id: int, payload: WebConsent, repo: Repo) -> WebConsent:
    with known_resource():
        await repo.save_web_consent(ticket_id, payload.use_web_search)
    return payload


@router.get("/tickets/{ticket_id}/ui-observation")
async def ticket_observation(ticket_id: int, repo: Repo) -> ObservationOut:
    with known_resource():
        return ObservationOut(
            observation=await repo.observation(await repo.ticket_source(ticket_id), ticket_id)
        )


@router.put("/tickets/{ticket_id}/ui-observation")
async def set_ticket_observation(
    ticket_id: int, payload: UiObservation, repo: Repo
) -> ObservationOut:
    with known_resource():
        await repo.save_observation(ticket_id, payload)
    return ObservationOut(observation=payload)


@router.delete("/tickets/{ticket_id}/ui-observation", status_code=204)
async def remove_ticket_observation(ticket_id: int, repo: Repo) -> Response:
    with known_resource():
        await repo.save_observation(ticket_id, None)
    return Response(status_code=204)
