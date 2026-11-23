from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import SourceNotFoundError
from app.domain.tickets import TicketNotFoundError
from app.domain.ui_observation import UiObservation


class DiagnosticOptionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def project(self, source_id: int) -> tuple[str | None, str | None, bool]:
        row = (
            await self._session.execute(
                text(
                    "SELECT diagnostic_ui_probe, diagnostic_web_provider, allow_web_search FROM sources WHERE id = :id"
                ),
                {"id": source_id},
            )
        ).one_or_none()
        if row is None:
            raise SourceNotFoundError("Project not found")
        return row[0], row[1], row[2]

    async def save_project(
        self, source_id: int, ui_probe: str | None, web_provider: str | None, allow_web_search: bool
    ) -> None:
        row = await self._session.scalar(
            text(
                "UPDATE sources SET diagnostic_ui_probe = :probe, diagnostic_web_provider = :provider, allow_web_search = :allow "
                "WHERE id = :id RETURNING id"
            ),
            {
                "id": source_id,
                "probe": ui_probe,
                "provider": web_provider,
                "allow": allow_web_search,
            },
        )
        if row is None:
            raise SourceNotFoundError("Project not found")
        await self._session.commit()

    async def ticket(self, source_id: int, ticket_id: int) -> tuple[bool, str] | None:
        row = (
            await self._session.execute(
                text(
                    "SELECT use_web_search, title FROM tickets WHERE source_id = :source AND id = :id"
                ),
                {"source": source_id, "id": ticket_id},
            )
        ).one_or_none()
        return (row[0], row[1]) if row else None

    async def ticket_source(self, ticket_id: int) -> int:
        source = await self._session.scalar(
            text("SELECT source_id FROM tickets WHERE id = :id"), {"id": ticket_id}
        )
        if source is None:
            raise TicketNotFoundError("Ticket not found")
        return int(source)

    async def save_web_consent(self, ticket_id: int, allow: bool) -> None:
        row = await self._session.scalar(
            text("UPDATE tickets SET use_web_search = :allow WHERE id = :id RETURNING id"),
            {"id": ticket_id, "allow": allow},
        )
        if row is None:
            raise TicketNotFoundError("Ticket not found")
        await self._session.commit()

    async def observation(self, source_id: int, ticket_id: int) -> UiObservation | None:
        stored = await self._session.scalar(
            text("SELECT ui_observation FROM tickets WHERE source_id = :source AND id = :id"),
            {"source": source_id, "id": ticket_id},
        )
        return UiObservation.model_validate(stored) if stored is not None else None

    async def save_observation(self, ticket_id: int, observation: UiObservation | None) -> None:
        row = await self._session.scalar(
            text(
                "UPDATE tickets SET ui_observation = CAST(:data AS jsonb) WHERE id = :id RETURNING id"
            ),
            {"id": ticket_id, "data": observation.model_dump_json() if observation else None},
        )
        if row is None:
            raise TicketNotFoundError("Ticket not found")
        await self._session.commit()
