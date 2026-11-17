from typing import Protocol

from app.domain.ticket_logs import TicketLogAttachment


class TicketLogRepository(Protocol):
    async def create_attachment(
        self, source_id: int, ticket_id: int, filename: str, storage_key: str, size_bytes: int
    ) -> TicketLogAttachment: ...

    async def get_attachment(
        self, source_id: int, ticket_id: int, attachment_id: int
    ) -> TicketLogAttachment | None: ...

    async def list_attachments(
        self, source_id: int, ticket_id: int
    ) -> list[TicketLogAttachment]: ...

    async def update_status(
        self, attachment_id: int, status: str, error: str | None
    ) -> TicketLogAttachment | None: ...
