from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.tickets import TicketResultTranslations


@dataclass(frozen=True, slots=True)
class TicketLocalizationSnapshot:
    ticket_id: int
    status: str
    updated_at: datetime
    run_id: int | None
    model_id: int | None
    text: str | None
    translations: TicketResultTranslations


class TicketLocalizationRepository(Protocol):
    async def load_locked(self, ticket_id: int) -> TicketLocalizationSnapshot | None: ...

    async def save_if_current(
        self, snapshot: TicketLocalizationSnapshot, translations: TicketResultTranslations
    ) -> bool: ...
