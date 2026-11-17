import asyncio
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import ProviderCredentials, WorkspaceModelEntry
from app.domain.repositories.material_generation import (
    GeneratedJson,
    MaterialGenerationGateway,
)
from app.domain.repositories.model_providers import ModelProviderRepository
from app.domain.repositories.retrieval import SearchHit, SearchUnavailableError
from app.domain.repositories.sources import SourceRepository
from app.domain.repositories.tickets import TicketRepository
from app.domain.tickets import (
    Ticket,
    TicketConflictError,
    TicketNotFoundError,
    TicketStats,
    TicketStep,
)
from app.usecase.retrieval import RetrievalUsecase
from app.usecase.ticket_pricing import parse_pricing, step_cost_usd

TRIAGE_SYSTEM = """You are the triage agent of a technical support pipeline for a software product.
Classify the user ticket and prepare search queries for the knowledge base (indexed source code,
documentation and user flows of this exact product).

Estimate complexity: "simple" for known errors and questions answerable from documentation;
"standard" for reproducible bugs; "hard" for suspected code/infrastructure defects or multi-system cases.

Return ONLY JSON with this exact schema:
{"category":"<short free-form category>","severity":"low|medium|high|critical",
"complexity":"simple|standard|hard",
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

Compare the report with the documented expected user flow. A vague report or an action that
matches the expected user flow is not by itself evidence of a product defect. Explain expected
behavior respectfully and ask for the specific missing symptom or step; never mock or blame the
user. Missing evidence does not prove that everything is working.

Treat OOM-kill, disk exhaustion, low memory, container resource limits, and similar signals as
possible operational causes. Report them as confirmed only when the evidence says so, and do not
claim a code defect unless independent evidence supports it. Distinguish observed evidence from
hypotheses and state uncertainty clearly.

Return ONLY JSON with this exact schema:
{"decision":"answer|escalate","answer":"<markdown answer in Russian, or null>",
"escalate_reason":"<Russian reason, or null>","source_refs":["S1"]}"""


class TriageResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    category: str = Field(min_length=1, max_length=80)
    severity: str
    complexity: str
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

    @field_validator("complexity")
    @classmethod
    def _check_complexity(cls, value: str) -> str:
        allowed = {"simple", "standard", "hard"}
        if value not in allowed:
            raise ValueError("complexity must be one of: " + ", ".join(sorted(allowed)))
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


@dataclass(frozen=True, slots=True)
class ModelTarget:
    model: WorkspaceModelEntry
    credentials: ProviderCredentials
    pricing: "tuple[Decimal, Decimal] | None"


@dataclass(frozen=True, slots=True)
class PipelineTargets:
    triage: ModelTarget
    strong: ModelTarget
    cheap: ModelTarget | None


class TicketGraphState(TypedDict):
    ticket: Ticket
    targets: PipelineTargets | None
    triage: TriageResult | None
    dossier: dict[str, SearchHit]
    resolution: ResolutionResult | None
    valid_refs: list[str]
    tier: str
    routing_reason: str


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
        self._graph = self._build_graph()

    async def create_ticket(self, source_id: int, title: str, description: str) -> Ticket:
        if await self._sources.get_any(source_id) is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        return await self._tickets.create(source_id, title.strip(), description.strip())

    async def list_tickets(self, source_id: int) -> list[Ticket]:
        if await self._sources.get_any(source_id) is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        return await self._tickets.list_for_source(source_id)

    async def ticket_stats(self, source_id: int) -> TicketStats:
        if await self._sources.get_any(source_id) is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        return await self._tickets.stats(source_id)

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
        if await self._tickets.has_unready_log_attachments(ticket_id):
            raise TicketConflictError(
                "retry or remove failed log archives and wait for processing attachments before running the issue"
            )
        previous_status = ticket.status
        await self._tickets.update_result(ticket_id, "running")
        try:
            await self._graph.ainvoke(
                {
                    "ticket": ticket,
                    "targets": None,
                    "triage": None,
                    "dossier": {},
                    "resolution": None,
                    "valid_refs": [],
                    "tier": "",
                    "routing_reason": "",
                },
                config={"recursion_limit": 12},
            )
            updated = await self._tickets.get(ticket_id)
            if updated is None:
                raise TicketNotFoundError(str(ticket_id))
            return updated
        except (TicketAgentUnavailableError, SourceNotFoundError):
            await self._tickets.update_result(ticket_id, previous_status)
            raise
        except Exception as exc:
            await self._tickets.update_result(ticket_id, "failed", escalate_reason=str(exc)[:500])
            raise

    def _build_graph(self) -> Any:
        graph = StateGraph(TicketGraphState)
        graph.add_node("resolve_models", self._graph_resolve_models)
        graph.add_node("triage", self._graph_triage)
        graph.add_node("investigate", self._graph_investigate)
        graph.add_node("resolve", self._graph_resolve)
        graph.add_node("answer", self._graph_answer)
        graph.add_node("escalate_empty", self._graph_escalate_empty)
        graph.add_node("escalate_invalid_refs", self._graph_escalate_invalid_refs)
        graph.add_node("escalate_model", self._graph_escalate_model)
        graph.add_edge(START, "resolve_models")
        graph.add_edge("resolve_models", "triage")
        graph.add_edge("triage", "investigate")
        graph.add_conditional_edges(
            "investigate",
            self._route_after_investigation,
            {"empty": "escalate_empty", "ready": "resolve"},
        )
        graph.add_conditional_edges(
            "resolve",
            self._route_after_resolution,
            {
                "answer": "answer",
                "invalid_refs": "escalate_invalid_refs",
                "escalate": "escalate_model",
            },
        )
        for node in ("answer", "escalate_empty", "escalate_invalid_refs", "escalate_model"):
            graph.add_edge(node, END)
        return graph.compile()

    async def _graph_resolve_models(self, state: TicketGraphState) -> dict[str, Any]:
        return {"targets": await self._resolve_models(state["ticket"].source_id)}

    async def _graph_triage(self, state: TicketGraphState) -> dict[str, Any]:
        targets = state["targets"]
        if targets is None:
            raise RuntimeError("ticket graph has no model targets")
        return {"triage": await self._run_triage(state["ticket"], targets.triage)}

    async def _graph_investigate(self, state: TicketGraphState) -> dict[str, Any]:
        triage = state["triage"]
        if triage is None:
            raise RuntimeError("ticket graph has no triage result")
        dossier = await self._build_dossier(
            state["ticket"].id, state["ticket"].source_id, triage.search_queries
        )
        return {"dossier": dossier}

    @staticmethod
    def _route_after_investigation(state: TicketGraphState) -> str:
        return "ready" if state["dossier"] else "empty"

    async def _graph_resolve(self, state: TicketGraphState) -> dict[str, Any]:
        targets, triage = state["targets"], state["triage"]
        if targets is None or triage is None:
            raise RuntimeError("ticket graph is missing resolver inputs")
        resolver = resolver_target(triage, targets)
        tier = "cheap" if resolver is targets.cheap else "strong"
        routing_reason = (
            "simple ticket routed to the configured low-cost model"
            if tier == "cheap"
            else "standard or hard ticket routed to the strong model"
            if triage.complexity != "simple"
            else "no low-cost model is configured; using the strong model"
        )
        resolution = await self._run_resolver(
            state["ticket"],
            resolver,
            state["dossier"],
            triage,
            tier=tier,
            routing_reason=routing_reason,
        )
        valid_refs = _unique([ref for ref in resolution.source_refs if ref in state["dossier"]])
        return {
            "resolution": resolution,
            "valid_refs": valid_refs,
            "tier": tier,
            "routing_reason": routing_reason,
        }

    @staticmethod
    def _route_after_resolution(state: TicketGraphState) -> str:
        resolution = state["resolution"]
        if resolution is None:
            raise RuntimeError("ticket graph has no resolution result")
        if resolution.decision == "escalate":
            return "escalate"
        return "answer" if state["valid_refs"] else "invalid_refs"

    async def _graph_answer(self, state: TicketGraphState) -> dict[str, Any]:
        triage, resolution = state["triage"], state["resolution"]
        if triage is None or resolution is None:
            raise RuntimeError("ticket graph cannot finalize an incomplete answer")
        await self._tickets.update_result(
            state["ticket"].id,
            "answered",
            triage=triage.model_dump(),
            answer=resolution.answer,
            citations=[_citation(state["dossier"][ref]) for ref in state["valid_refs"]],
        )
        return {}

    async def _graph_escalate_empty(self, state: TicketGraphState) -> dict[str, Any]:
        triage = state["triage"]
        if triage is None:
            raise RuntimeError("ticket graph cannot escalate without triage")
        await self._escalate(
            state["ticket"].id,
            "в индексах проекта нет релевантного контента по обращению",
            triage,
            state["dossier"],
            skipped_llm=True,
        )
        return {}

    async def _graph_escalate_invalid_refs(self, state: TicketGraphState) -> dict[str, Any]:
        triage = state["triage"]
        if triage is None:
            raise RuntimeError("ticket graph cannot escalate without triage")
        await self._escalate(
            state["ticket"].id,
            "модель не сослалась на найденные фрагменты контекста",
            triage,
            state["dossier"],
        )
        return {}

    async def _graph_escalate_model(self, state: TicketGraphState) -> dict[str, Any]:
        triage, resolution = state["triage"], state["resolution"]
        if triage is None or resolution is None:
            raise RuntimeError("ticket graph cannot escalate without a resolution result")
        await self._escalate(
            state["ticket"].id,
            resolution.escalate_reason or "недостаточно данных для ответа",
            triage,
            state["dossier"],
        )
        return {}

    async def _resolve_models(self, source_id: int) -> "PipelineTargets":
        selections = await self._models.get_project_selections(source_id)
        strong_result = await self._target_for(
            selections.get("ticket_resolution"),
            fallback_error="select a chat model for the ticket pipeline before running it",
        )
        assert strong_result is not None
        triage_result = await self._target_for(
            selections.get("ticket_triage"), fallback=strong_result
        )
        assert triage_result is not None
        cheap_selection = selections.get("ticket_resolution_cheap")
        cheap = await self._target_for(cheap_selection) if cheap_selection else None
        return PipelineTargets(triage=triage_result, strong=strong_result, cheap=cheap)

    async def _target_for(
        self, model_id: int | None, fallback: "ModelTarget | None" = None, fallback_error: str = ""
    ) -> "ModelTarget | None":
        if model_id is None:
            if fallback is not None:
                return fallback
            raise TicketAgentUnavailableError(fallback_error)
        model = await self._models.get_model(model_id)
        if model is None or "chat" not in model.capabilities:
            raise TicketAgentUnavailableError("the selected ticket model is unavailable")
        if model.status not in {"available", "installed"}:
            raise TicketAgentUnavailableError("the selected ticket model is not ready")
        credentials = await self._models.get_credentials(model.provider_connection_id)
        if credentials is None:
            raise TicketAgentUnavailableError("the ticket model provider is unavailable")
        return ModelTarget(
            model=model,
            credentials=credentials,
            pricing=parse_pricing(model.metadata),
        )

    async def _run_triage(self, ticket: Ticket, target: ModelTarget) -> TriageResult:
        started = time.monotonic()
        prompt = f"Ticket title: {ticket.title}\n\nTicket description:\n{ticket.description}"
        triage, usage = await _generate_parsed(
            self._gateway,
            target,
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
            model_id=target.model.id,
            duration_ms=_elapsed_ms(started),
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
            cost_usd=step_cost_usd(target.pricing, usage.input_tokens, usage.output_tokens),
        )
        return triage

    async def _build_dossier(
        self, ticket_id: int, source_id: int, queries: list[str]
    ) -> dict[str, SearchHit]:
        started = time.monotonic()
        per_query = max(6, self._config.context_chunks // max(1, len(queries)))
        per_query_results: list[list[SearchHit]] = []
        for query in queries:
            try:
                response = await self._retrieval.search_ticket_context(
                    source_id, ticket_id, query, per_query
                )
                per_query_results.append(list(response.hits))
            except SearchUnavailableError:
                per_query_results.append([])
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
        target: ModelTarget,
        dossier: dict[str, SearchHit],
        triage: TriageResult,
        tier: str,
        routing_reason: str,
    ) -> ResolutionResult:
        started = time.monotonic()
        prompt = (
            f"Ticket title: {ticket.title}\n\nTicket description:\n{ticket.description}\n\n"
            f"Triage summary: {triage.summary}\n\nEvidence fragments:\n"
            + _format_dossier(dossier, self._config.max_context_characters)
        )
        resolution, usage = await _generate_parsed(
            self._gateway,
            target,
            RESOLVER_SYSTEM,
            prompt,
            ResolutionResult,
            self._config,
        )
        valid = _unique([ref for ref in resolution.source_refs if ref in dossier])
        routing = {
            "complexity": triage.complexity,
            "tier": tier,
            "reason": routing_reason,
        }
        await self._tickets.add_step(
            ticket.id,
            "resolve",
            {"fragments": list(dossier), "decision": resolution.decision},
            {**resolution.model_dump(), "source_refs": valid, "routing": routing},
            model_id=target.model.id,
            duration_ms=_elapsed_ms(started),
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
            cost_usd=step_cost_usd(target.pricing, usage.input_tokens, usage.output_tokens),
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


def _interleave_deduped(per_query_results: list[list[SearchHit]], limit: int) -> list[SearchHit]:
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
        "ticket_id": hit.ticket_id,
        "attachment_id": hit.attachment_id,
        "event_timestamp": hit.event_timestamp,
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
    target: "ModelTarget",
    system_prompt: str,
    user_prompt: str,
    schema: type[TSchema],
    config: TicketAgentConfig,
) -> "tuple[TSchema, GeneratedJson]":
    generated = await asyncio.to_thread(
        gateway.generate_json_with_usage,
        target.credentials,
        target.model.provider_model_id,
        system_prompt,
        user_prompt,
        config.timeout_seconds,
        config.max_output_tokens,
    )
    usage = GeneratedJson(
        text=generated.text,
        input_tokens=generated.input_tokens,
        output_tokens=generated.output_tokens,
    )
    try:
        return _parse_json_output(generated.text, schema), usage
    except TicketAgentResponseError:
        repaired = await asyncio.to_thread(
            gateway.generate_json_with_usage,
            target.credentials,
            target.model.provider_model_id,
            "Convert the supplied model response into valid JSON of the required schema. "
            "Keep the same useful content. Return JSON only without Markdown fences.",
            f"Response to repair:\n{generated.text[:8000]}",
            config.timeout_seconds,
            config.max_output_tokens,
        )
        combined = GeneratedJson(
            text=repaired.text,
            input_tokens=_sum_usage(usage.input_tokens, repaired.input_tokens),
            output_tokens=_sum_usage(usage.output_tokens, repaired.output_tokens),
        )
        return _parse_json_output(repaired.text, schema), combined


def _sum_usage(first: int | None, second: int | None) -> int | None:
    if first is None and second is None:
        return None
    return (first or 0) + (second or 0)


def resolver_target(triage: TriageResult, targets: "PipelineTargets") -> "ModelTarget":
    if targets.cheap is not None and triage.complexity == "simple":
        return targets.cheap
    return targets.strong


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
