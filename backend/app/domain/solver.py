from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SolverEnabled(BaseModel):
    model_config = ConfigDict(extra="forbid")

    triage: bool = True
    resolve: bool = True


class SolverModels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_resolution: int | None = Field(default=None, gt=0)
    ticket_triage: int | None = Field(default=None, gt=0)
    ticket_resolution_cheap: int | None = Field(default=None, gt=0)


class SolverProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    enabled: SolverEnabled
    models: SolverModels


class SolverProfile(SolverProfileInput):
    id: int


class SolverModelSnapshot(BaseModel):
    id: int
    display_name: str


class SolverModelSnapshots(BaseModel):
    ticket_resolution: SolverModelSnapshot | None = None
    ticket_triage: SolverModelSnapshot | None = None
    ticket_resolution_cheap: SolverModelSnapshot | None = None


class TicketRun(BaseModel):
    id: int
    profile_id: int
    profile_name: str
    enabled: SolverEnabled
    models: SolverModelSnapshots
    status: str
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None


class SolverProfileNotFoundError(LookupError):
    pass


class SolverProfileConflictError(ValueError):
    pass
