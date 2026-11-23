from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.ticket_localization import TicketLocalizationSnapshot
from app.domain.tickets import LocalizedTicketResult, TicketResultTranslations

_LOAD = text("""
    SELECT ticket.status, ticket.updated_at, ticket.localized_result, ticket.english_result,
           latest.id AS run_id,
           CASE
               WHEN latest.id IS NOT NULL
                   AND (latest.finished_at IS NULL OR latest.status <> ticket.status) THEN NULL
               WHEN ticket.status = 'answered' THEN ticket.answer
               WHEN ticket.status = 'escalated' THEN ticket.escalate_reason
           END AS result_text,
           author.model_id
    FROM tickets AS ticket
    LEFT JOIN LATERAL (
        SELECT run.id, run.status, run.finished_at
        FROM ticket_runs AS run
        WHERE run.ticket_id = ticket.id
        ORDER BY run.id DESC LIMIT 1
    ) AS latest ON TRUE
    LEFT JOIN LATERAL (
        SELECT step.model_id
        FROM ticket_steps AS step
        WHERE step.ticket_id = ticket.id
          AND step.run_id IS NOT DISTINCT FROM latest.id
          AND step.status = 'completed'
          AND step.model_id IS NOT NULL
          AND (
              step.step = 'resolve'
              OR (ticket.status = 'escalated' AND step.step = 'triage')
          )
        ORDER BY step.id DESC LIMIT 1
    ) AS author ON TRUE
    WHERE ticket.id = :ticket_id
""")

_SAVE = text("""
    UPDATE tickets AS ticket
    SET localized_result = CAST(:localized AS jsonb), english_result = :english
    WHERE ticket.id = :ticket_id
      AND ticket.status = :status
      AND ticket.updated_at = :updated_at
      AND ticket.localized_result IS NULL
      AND ticket.english_result IS NULL
      AND (
          SELECT MAX(id) FROM ticket_runs WHERE ticket_id = ticket.id
      ) IS NOT DISTINCT FROM CAST(:run_id AS bigint)
    RETURNING ticket.id
""")


class TicketLocalizationSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_locked(self, ticket_id: int) -> TicketLocalizationSnapshot | None:
        parameters = {"ticket_id": ticket_id}
        await self._session.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended("
                "'ticket-result-localization:' || CAST(:ticket_id AS text), 0))"
            ),
            parameters,
        )
        result = await self._session.execute(_LOAD, parameters)
        row = result.one_or_none()
        if row is None:
            return None
        return TicketLocalizationSnapshot(
            ticket_id=ticket_id,
            status=row.status,
            updated_at=row.updated_at,
            run_id=row.run_id,
            model_id=row.model_id,
            text=row.result_text,
            translations=TicketResultTranslations(
                localized_result=(
                    LocalizedTicketResult.model_validate(row.localized_result)
                    if row.localized_result is not None
                    else None
                ),
                english_result=row.english_result,
            ),
        )

    async def save_if_current(
        self, snapshot: TicketLocalizationSnapshot, translations: TicketResultTranslations
    ) -> bool:
        result = await self._session.execute(
            _SAVE,
            {
                "ticket_id": snapshot.ticket_id,
                "status": snapshot.status,
                "updated_at": snapshot.updated_at,
                "run_id": snapshot.run_id,
                "localized": (
                    translations.localized_result.model_dump_json()
                    if translations.localized_result is not None
                    else None
                ),
                "english": translations.english_result,
            },
        )
        return result.scalar_one_or_none() is not None
