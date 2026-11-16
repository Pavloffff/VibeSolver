from typing import Any

from pydantic import BaseModel, Field

from app.domain.entities import ConfigField


class ConfigSchema(BaseModel):
    fields: list[ConfigField]


class ConnectorInfo(BaseModel):
    type: str
    ready: bool
    config_schema: ConfigSchema


class SourceCreate(BaseModel):
    type: str
    name: str
    config: dict[str, Any]


class ProjectResource(BaseModel):
    id: str | None = None
    type: str
    name: str
    path: str | None = None
    config: dict[str, Any]


class MaterialGenerationIn(BaseModel):
    model_config = {"extra": "forbid", "strict": True}

    category: str = Field(min_length=1, max_length=80)
    instructions: str | None = Field(default=None, max_length=4000)


class MaterialGenerationOut(BaseModel):
    resources: list[ProjectResource]


class SearchIn(BaseModel):
    model_config = {"extra": "forbid", "strict": True}

    query: str = Field(min_length=1, max_length=2000)
    index_types: list[str] | None = None
    top_k: int = Field(default=8, ge=1, le=50)


class SearchHitOut(BaseModel):
    index_type: str
    run_id: int
    path: str
    branch: str
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None
    content: str
    score: float
    rerank_score: float | None = None
    source_ref: str


class SearchMetaOut(BaseModel):
    indexes_searched: list[str]
    top_k: int
    candidate_k: int
    rerank_applied: bool
    warnings: list[str]
    latency_ms: float


class SearchOut(BaseModel):
    results: list[SearchHitOut]
    meta: SearchMetaOut


class SourceUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    resources: dict[str, list[ProjectResource]] | None = None


class LastImportOut(BaseModel):
    status: str
    finished_at: str | None


class SourceOut(BaseModel):
    id: int
    type: str
    name: str
    enabled: bool
    config: dict[str, Any]
    last_import: LastImportOut | None


class SourceStatsOut(BaseModel):
    file_count: int


class ResourceContentOut(BaseModel):
    content: str


class ResourceContentUpdate(BaseModel):
    content: str = Field(max_length=5_000_000)


class DocumentationImportOut(BaseModel):
    added: list[str]
    unchanged: list[str]
    conflicts: list[dict[str, str]]


class ImportEnqueueOut(BaseModel):
    task_id: str


class ImportStatusOut(BaseModel):
    status: str
    progress: int
    error: str | None


class UploadOut(BaseModel):
    upload_key: str


class ModelProviderCreate(BaseModel):
    provider_type: str
    name: str
    base_url: str | None = None
    api_key: str | None = None


class ModelProviderUpdate(BaseModel):
    name: str
    base_url: str | None = None
    api_key: str | None = None


class ModelProviderOut(BaseModel):
    id: int
    provider_type: str
    name: str
    base_url: str
    has_api_key: bool


class ModelProviderTypeOut(BaseModel):
    provider_type: str
    display_name: str
    default_url: str
    requires_api_key: bool
    fixed_url: bool
    sync_all_models: bool
    supports_model_pull: bool


class ProviderModelAdd(BaseModel):
    provider_model_id: str


class ModelOut(BaseModel):
    id: int
    provider_connection_id: int
    provider_type: str
    provider_name: str
    provider_model_id: str
    display_name: str
    capabilities: list[str]
    status: str
    progress: int | None
    metadata: dict[str, Any]


class ProviderAvailableModelOut(BaseModel):
    provider_model_id: str
    display_name: str
    capabilities: list[str]
    status: str
    metadata: dict[str, Any]


class ModelSelectionUpdate(BaseModel):
    model_id: int | None


class ModelSelectionOut(BaseModel):
    indexing: int | None
    documentation_generation: int | None
    ticket_resolution: int | None
    ticket_triage: int | None = None
    ticket_resolution_cheap: int | None = None


class TicketCreateIn(BaseModel):
    model_config = {"extra": "forbid", "strict": True}

    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=20000)


class TicketCitationOut(BaseModel):
    source_ref: str
    path: str
    index_type: str
    start_line: int | None = None
    end_line: int | None = None


class TicketBriefOut(BaseModel):
    id: int
    title: str
    status: str
    created_at: str | None = None


class TicketStatsOut(BaseModel):
    total: int
    by_status: dict[str, int]
    completed: int
    autoresolve_rate: float
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    avg_cost_usd: float | None
    avg_tokens_per_ticket: float


class TicketOut(BaseModel):
    id: int
    source_id: int
    title: str
    description: str
    status: str
    triage: dict[str, Any] | None = None
    answer: str | None = None
    escalate_reason: str | None = None
    citations: list[TicketCitationOut] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class TicketStepOut(BaseModel):
    step: str
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    model_id: int | None = None
    duration_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    created_at: str | None = None


class TicketDetailOut(BaseModel):
    ticket: TicketOut
    steps: list[TicketStepOut]


class IndexRunOut(BaseModel):
    index_type: str
    status: str
    progress: int
    run_id: int | None
    snapshot_id: int | None
    files_total: int
    chunks_total: int
    error: str | None
    updated_at: str | None


class ProjectIndexStatusOut(BaseModel):
    ready: bool
    import_status: str
    indexes: list[IndexRunOut]


class IndexEnqueueOut(BaseModel):
    run_id: int
    task_id: str
    status: str


class OllamaPullIn(BaseModel):
    model_id: str


def sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: _sanitize_value(value) for key, value in config.items() if key != "token_ref"}


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_value(nested) for key, nested in value.items() if key != "token_ref"}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value
