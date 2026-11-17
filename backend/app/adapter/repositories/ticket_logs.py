from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ticket_logs import TicketLogAttachment


class TicketLogSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_attachment(
        self, source_id: int, ticket_id: int, filename: str, storage_key: str, size_bytes: int
    ) -> TicketLogAttachment:
        result = await self._session.execute(
            text(
                "INSERT INTO ticket_log_attachments "
                "(source_id, ticket_id, filename, storage_key, size_bytes, status) "
                "VALUES (:source_id, :ticket_id, :filename, :storage_key, :size_bytes, 'queued') "
                "RETURNING id"
            ),
            {
                "source_id": source_id,
                "ticket_id": ticket_id,
                "filename": filename,
                "storage_key": storage_key,
                "size_bytes": size_bytes,
            },
        )
        attachment_id = int(result.scalar_one())
        await self._session.commit()
        attachment = await self.get_attachment(source_id, ticket_id, attachment_id)
        assert attachment is not None
        return attachment

    async def get_attachment(
        self, source_id: int, ticket_id: int, attachment_id: int
    ) -> TicketLogAttachment | None:
        result = await self._session.execute(
            text(_ATTACHMENT_COLUMNS + " WHERE source_id = :source_id AND ticket_id = :ticket_id AND id = :id"),
            {"source_id": source_id, "ticket_id": ticket_id, "id": attachment_id},
        )
        row = result.one_or_none()
        return _to_attachment(row) if row is not None else None

    async def list_attachments(
        self, source_id: int, ticket_id: int
    ) -> list[TicketLogAttachment]:
        result = await self._session.execute(
            text(_ATTACHMENT_COLUMNS + " WHERE source_id = :source_id AND ticket_id = :ticket_id ORDER BY id"),
            {"source_id": source_id, "ticket_id": ticket_id},
        )
        return [_to_attachment(row) for row in result.all()]

    async def update_status(
        self, attachment_id: int, status: str, error: str | None
    ) -> TicketLogAttachment | None:
        result = await self._session.execute(
            text(
                "UPDATE ticket_log_attachments SET status = :status, error = :error, "
                "updated_at = now() WHERE id = :id RETURNING id, source_id, ticket_id"
            ),
            {"id": attachment_id, "status": status, "error": error},
        )
        row = result.one_or_none()
        await self._session.commit()
        if row is None:
            return None
        return await self.get_attachment(int(row.source_id), int(row.ticket_id), int(row.id))


_ATTACHMENT_COLUMNS = (
    "SELECT id, source_id, ticket_id, filename, storage_key, size_bytes, status, error, "
    "created_at, updated_at FROM ticket_log_attachments"
)


def _to_attachment(row: Any) -> TicketLogAttachment:
    return TicketLogAttachment(
        id=int(row.id),
        source_id=int(row.source_id),
        ticket_id=int(row.ticket_id),
        filename=str(row.filename),
        storage_key=str(row.storage_key),
        size_bytes=int(row.size_bytes),
        status=str(row.status),
        error=str(row.error) if row.error is not None else None,
        created_at=row.created_at if isinstance(row.created_at, datetime) else None,
        updated_at=row.updated_at if isinstance(row.updated_at, datetime) else None,
    )
