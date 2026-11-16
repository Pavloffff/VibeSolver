import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import ProviderCredentials, WorkspaceModelEntry
from app.domain.repositories.material_generation import MaterialGenerationGateway
from app.domain.repositories.model_providers import ModelProviderRepository
from app.domain.repositories.retrieval import SearchHit, SearchUnavailableError
from app.domain.repositories.sources import SourceRepository
from app.domain.repositories.tickets import TicketRepository
from app.domain.tickets import (
    Ticket,
    TicketConflictError,
    TicketNotFoundError,
    TicketStep,
)
from app.usecase.retrieval import RetrievalUsecase

TRIAGE_SYSTEM = """You are the triage agent of a technical support pipeline for a software product.
Classify the user ticket and prepare search queries for the knowledge base (indexed source code,
documentation and user flows of this exact product).

Return ONLY JSON with this exact schema:
{"category":"<short free-form category>","severity":"low|medium|high|critical",
"summary":"<one-sentence summary of the issue, in Russian>",
"search_queries":["<1-5 specific search queries mixing the user's wording and likely code/doc terms>"],
"missing_info":["<what a human would need to ask the user, in Russian, may be empty>"]}
Base everything on the ticket text. Do not invent facts. Do not add other keys."""


RESOLVER_SYSTEM = """You are the resolver agent of a technical support pipeline. You receive a user
ticket and numbered evidence fragments (S1, S2, ...) retrieved from the product's indexed code,
documentation and user flows.

Answer the ticket in Russian, concretely and helpfully, using ONLY facts supported by the
fragments. Cite the fragment IDs you relied on (for example S1, S3) in the source_refs field.
If the fragments are insufficient to answer reliably, choose escalate and explain in Russian
what exactly is missing; never invent behavior that the fragments do not support.

Return ONLY JSON with this exact schema:
{"decision":"answer|escalate","answer":"<markdown answer in Russian, or null>",
"escalate_reason":"<Russian reason, or null>","source_refs":["S1"]}"""


class TriageResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    category: str = Field(min_length=1, max_length=80)
    severity: str
    summary: str = Field(min_length=1, max_length=500)
    search_queries: list[str] = Field(min_length=1, max_length=5)
    missing_info: list[str] = Field(default_factory=list)

    @field_validator("severity")
    @classmethod
    def _check_severity(cls, value: str) -> str:
        allowed = {"low", "medium", "high", "critical"}
        if value not in allowed:
            raise ValueError("severity must be one of: " + ", ".join(sorted(allowed)))
        return value

    @field_validator("search_queries")
    @classmethod
    def _check_queries(cls, value: list[str]) -> list[str]:
        if any(len(query.strip()) < 3 for query in value):
            raise ValueError("search queries must be meaningful strings")
        return value


class ResolutionResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    decision: str
    answer: str | None = None
    escalate_reason: str | None = None
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("decision")
    @classmethod
    def _check_decision(cls, value: str) -> str:
        if value not in {"answer", "escalate"}:
            raise ValueError("decision must be answer or escalate")
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> "ResolutionResult":
        if self.decision == "answer" and not (self.answer or "").strip():
            raise ValueError("answer decision requires a non-empty answer")
        if self.decision == "escalate" and not (self.escalate_reason or "").strip():
            raise ValueError("escalate decision requires a non-empty escalate_reason")
        return self


@dataclass(frozen=True, slots=True)
class TicketAgentConfig:
    timeout_seconds: int
    max_output_tokens: int
    context_chunks: int
    max_context_characters: int


class TicketAgentUnavailableError(ValueError):
    pass


class TicketAgentResponseError(RuntimeError):
    pass


class TicketAgentUsecase:
    def __init__(
        self,
        tickets: TicketRepository,
        sources: SourceRepository,
        models: ModelProviderRepository,
        retrieval: RetrievalUsecase,
        gateway: MaterialGenerationGateway,
        config: TicketAgentConfig,
    ) -> None:
        self._tickets = tickets
        self._sources = sources
        self._models = models
        self._retrieval = retrieval
        self._gateway = gateway
        self._config = config

    async def create_ticket(self, source_id: int, title: str, description: str) -> Ticket:
        if await self._sources.get_any(source_id) is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        return await self._tickets.create(source_id, title.strip(), description.strip())

    async def list_tickets(self, source_id: int) -> list[Ticket]:
        if await self._sources.get_any(source_id) is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        return await self._tickets.list_for_source(source_id)

    async def ticket_details(self, ticket_id: int) -> tuple[Ticket, list[TicketStep]]:
        ticket = await self._tickets.get(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(str(ticket_id))
        return ticket, await self._tickets.list_steps(ticket_id)

    async def run(self, ticket_id: int) -> Ticket:
        ticket = await self._tickets.get(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(str(ticket_id))
        if ticket.status == "running":
            raise TicketConflictError(f"ticket {ticket_id} is already running")
        previous_status = ticket.status
        await self._tickets.update_result(ticket_id, "running")
        try:
            model, credentials = await self._resolve_model(ticket.source_id)
            triage = await self._run_triage(ticket, credentials, model)
            dossier = await self._build_dossier(
                ticket.id, ticket.source_id, triage.search_queries
            )
            if not dossier:
                return await self._escalate(
                    ticket_id,
                    "в индексах проекта нет релевантного контента по обращению",
                    triage,
                    dossier,
                    skipped_llm=True,
                )
            resolution = await self._run_resolver(ticket, credentials, model, dossier, triage)
            valid_refs = _unique([ref for ref in resolution.source_refs if ref in dossier])
            if resolution.decision == "answer" and not valid_refs:
                return await self._escalate(
                    ticket_id,
                    "модель не сослалась на найденные фрагменты контекста",
                    triage,
                    dossier,
                )
            if resolution.decision == "escalate":
                return await self._escalate(
                    ticket_id,
                    resolution.escalate_reason or "недостаточно данных для ответа",
                    triage,
                    dossier,
                )
            updated = await self._tickets.update_result(
                ticket_id,
                "answered",
                triage=triage.model_dump(),
                answer=resolution.answer,
                citations=[_citation(dossier[ref]) for ref in valid_refs],
            )
            assert updated is not None
            return updated
        except (TicketAgentUnavailableError, SourceNotFoundError):
            await self._tickets.update_result(ticket_id, previous_status)
            raise
        except Exception as exc:
            await self._tickets.update_result(
                ticket_id, "failed", escalate_reason=str(exc)[:500]
            )
            raise

    async def _resolve_model(
        self, source_id: int
    ) -> tuple[WorkspaceModelEntry, ProviderCredentials]:
        selections = await self._models.get_project_selections(source_id)
        model_id = selections.get("ticket_resolution")
        if model_id is None:
            raise TicketAgentUnavailableError(
                "select a chat model for the ticket pipeline before running it"
            )
        model = await self._models.get_model(model_id)
        if model is None or "chat" not in model.capabilities:
            raise TicketAgentUnavailableError("the selected ticket model is unavailable")
        if model.status not in {"available", "installed"}:
            raise TicketAgentUnavailableError("the selected ticket model is not ready")
        credentials = await self._models.get_credentials(model.provider_connection_id)
        if credentials is None:
            raise TicketAgentUnavailableError("the ticket model provider is unavailable")
        return model, credentials

    async def _run_triage(
        self, ticket: Ticket, credentials: ProviderCredentials, model: WorkspaceModelEntry
    ) -> TriageResult:
        started = time.monotonic()
        prompt = f"Ticket title: {ticket.title}\n\nTicket description:\n{ticket.description}"
        triage = await _generate_parsed(
            self._gateway,
            credentials,
            model,
            TRIAGE_SYSTEM,
            prompt,
            TriageResult,
            self._config,
        )
        await self._tickets.add_step(
            ticket.id,
            "triage",
            {"title": ticket.title, "description": ticket.description[:500]},
            triage.model_dump(),
            model_id=model.id,
            duration_ms=_elapsed_ms(started),
        )
        return triage

    async def _build_dossier(
        self, ticket_id: int, source_id: int, queries: list[str]
    ) -> dict[str, SearchHit]:
        started = time.monotonic()
        per_query = max(6, self._config.context_chunks // max(1, len(queries)))
        per_query_results: list[list[SearchHit]] = []
        try:
            for query in queries:
                response = await self._retrieval.search(source_id, query, None, per_query)
                per_query_results.append(list(response.hits))
        except SearchUnavailableError:
            return {}
        ordered = _interleave_deduped(per_query_results, self._config.context_chunks)
        dossier = {f"S{index + 1}": hit for index, hit in enumerate(ordered)}
        if dossier:
            await self._tickets.add_step(
                ticket_id,
                "investigate",
                {"queries": queries},
                {
                    "refs": list(dossier),
                    "files": sorted({hit.path for hit in ordered}),
                    "fragments": len(ordered),
                },
                model_id=None,
                duration_ms=_elapsed_ms(started),
            )
        return dossier

    async def _run_resolver(
        self,
        ticket: Ticket,
        credentials: ProviderCredentials,
        model: WorkspaceModelEntry,
        dossier: dict[str, SearchHit],
        triage: TriageResult,
    ) -> ResolutionResult:
        started = time.monotonic()
        prompt = (
            f"Ticket title: {ticket.title}\n\nTicket description:\n{ticket.description}\n\n"
            f"Triage summary: {triage.summary}\n\nEvidence fragments:\n"
            + _format_dossier(dossier, self._config.max_context_characters)
        )
        resolution = await _generate_parsed(
            self._gateway,
            credentials,
            model,
            RESOLVER_SYSTEM,
            prompt,
            ResolutionResult,
            self._config,
        )
        valid = _unique([ref for ref in resolution.source_refs if ref in dossier])
        await self._tickets.add_step(
            ticket.id,
            "resolve",
            {"fragments": list(dossier), "decision": resolution.decision},
            {**resolution.model_dump(), "source_refs": valid},
            model_id=model.id,
            duration_ms=_elapsed_ms(started),
        )
        return resolution

    async def _escalate(
        self,
        ticket_id: int,
        reason: str,
        triage: TriageResult,
        dossier: dict[str, SearchHit],
        skipped_llm: bool = False,
    ) -> Ticket:
        if skipped_llm:
            await self._tickets.add_step(
                ticket_id,
                "resolve",
                {"fragments": list(dossier)},
                {"decision": "escalate", "escalate_reason": reason, "skipped_llm": True},
                model_id=None,
                duration_ms=0,
            )
        updated = await self._tickets.update_result(
            ticket_id,
            "escalated",
            triage=triage.model_dump(),
            escalate_reason=reason,
            citations=[_citation(hit) for hit in dossier.values()],
        )
        assert updated is not None
        return updated


def _interleave_deduped(
    per_query_results: list[list[SearchHit]], limit: int
) -> list[SearchHit]:
    seen: set[str] = set()
    ordered: list[SearchHit] = []
    position = 0
    while len(ordered) < limit:
        added = False
        for results in per_query_results:
            if position >= len(results):
                continue
            hit = results[position]
            if hit.source_ref in seen:
                continue
            seen.add(hit.source_ref)
            ordered.append(hit)
            added = True
            if len(ordered) >= limit:
                break
        if not added:
            break
        position += 1
    return ordered


def _citation(hit: SearchHit) -> dict[str, Any]:
    return {
        "source_ref": hit.source_ref,
        "path": hit.path,
        "index_type": hit.index_type,
        "start_line": hit.start_line,
        "end_line": hit.end_line,
    }


def _format_dossier(dossier: dict[str, SearchHit], max_characters: int) -> str:
    parts: list[str] = []
    used = 0
    for ref, hit in dossier.items():
        location = hit.path + (
            f":{hit.start_line}-{hit.end_line}" if hit.start_line is not None else ""
        )
        fragment = f"[{ref}] {location}\n{hit.content}\n"
        if used + len(fragment) > max_characters and parts:
            break
        parts.append(fragment)
        used += len(fragment)
    return "\n".join(parts)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


async def _generate_parsed[TSchema: BaseModel](
    gateway: MaterialGenerationGateway,
    credentials: ProviderCredentials,
    model: WorkspaceModelEntry,
    system_prompt: str,
    user_prompt: str,
    schema: type[TSchema],
    config: TicketAgentConfig,
) -> TSchema:
    raw = await asyncio.to_thread(
        gateway.generate_json,
        credentials,
        model.provider_model_id,
        system_prompt,
        user_prompt,
        config.timeout_seconds,
        config.max_output_tokens,
    )
    try:
        return _parse_json_output(raw, schema)
    except TicketAgentResponseError:
        repaired = await asyncio.to_thread(
            gateway.generate_json,
            credentials,
            model.provider_model_id,
            "Convert the supplied model response into valid JSON of the required schema. "
            "Keep the same useful content. Return JSON only without Markdown fences.",
            f"Response to repair:\n{raw[:8000]}",
            config.timeout_seconds,
            config.max_output_tokens,
        )
        return _parse_json_output(repaired, schema)


def _parse_json_output[TSchema: BaseModel](raw: str, schema: type[TSchema]) -> TSchema:
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise TicketAgentResponseError("model output does not contain a JSON object")
    try:
        payload = json.loads(text[start : end + 1])
        return schema.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise TicketAgentResponseError(
            "the model returned an invalid agent response; try again"
        ) from exc
