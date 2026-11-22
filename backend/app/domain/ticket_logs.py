from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class TicketLogAttachment:
    id: int
    source_id: int
    ticket_id: int
    filename: str
    storage_key: str
    size_bytes: int
    status: str
    error: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
