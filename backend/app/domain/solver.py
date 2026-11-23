from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.domain.specialist_roles import SPECIALIST_REGISTRY


class SolverEnabled(BaseModel):
    model_config = ConfigDict(extra="allow")
    __pydantic_extra__: dict[str, StrictBool] = Field(init=False)

    triage: bool = True
    resolve: bool = True
    flow: bool = False
    logs: bool = False
    code: bool = False
    ui: bool = False
    web: bool = False
    review: bool = False

    @model_validator(mode="after")
    def _check_specialist_flags(self) -> "SolverEnabled":
        unknown = self.__pydantic_extra__.keys() - SPECIALIST_REGISTRY.keys()
        if unknown:
            raise ValueError(f"Unknown Solver role: {', '.join(sorted(unknown))}")
        return self

    def specialist_enabled(self, role: str) -> bool:
        if role in type(self).model_fields:
            return bool(getattr(self, role))
        return self.__pydantic_extra__.get(role, False)


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


class PreviousTicketResult(BaseModel):
    status: str
    answer: str | None = None
    escalate_reason: str | None = None


class TicketRerunContext(BaseModel):
    comment: str | None = None
    previous_result: PreviousTicketResult


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
    rerun_context: TicketRerunContext | None = None


class SolverProfileNotFoundError(LookupError):
    pass


class SolverProfileConflictError(ValueError):
    pass
