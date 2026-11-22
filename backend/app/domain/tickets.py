from dataclasses import dataclass
from datetime import datetime
from typing import Any

TICKET_STATUSES: tuple[str, ...] = (
    "new",
    "running",
    "answered",
    "escalated",
    "failed",
)
TICKET_RESTARTABLE_STATUSES: tuple[str, ...] = ("answered", "escalated", "failed")


class TicketNotFoundError(LookupError):
    pass


class TicketConflictError(RuntimeError):
    pass


@dataclass(slots=True)
class Ticket:
    id: int
    source_id: int
    title: str
    description: str
    status: str
    triage: dict[str, Any] | None = None
    answer: str | None = None
    escalate_reason: str | None = None
    citations: list[dict[str, Any]] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    has_unready_log_attachments: bool = False


@dataclass(slots=True)
class TicketStep:
    id: int
    ticket_id: int
    step: str
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    model_id: int | None = None
    duration_ms: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TicketStats:
    total: int
    by_status: dict[str, int]
    completed: int
    autoresolve_rate: float
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    avg_cost_usd: float | None
    avg_tokens_per_ticket: float
