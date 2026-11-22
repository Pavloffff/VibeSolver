import asyncio
import json
import time
from collections.abc import Awaitable, Hashable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import (
    ProviderCredentials,
    ProviderUnavailableError,
    WorkspaceModelEntry,
)
from app.domain.repositories.material_generation import (
    GeneratedJson,
    MaterialGenerationGateway,
)
from app.domain.repositories.model_providers import ModelProviderRepository
from app.domain.repositories.retrieval import SearchHit, SearchUnavailableError
from app.domain.repositories.sources import SourceRepository
from app.domain.repositories.tickets import TicketRepository
from app.domain.solver import (
    SolverEnabled,
    SolverModelSnapshot,
    SolverModelSnapshots,
    SolverProfile,
    TicketRun,
)
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
Use the field names from the external request or response schema verbatim. Prefer the documented
user workflow for how-to questions. Only propose implementation changes when the ticket asks for them.
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
    triage: ModelTarget | None
    strong: ModelTarget | None
    cheap: ModelTarget | None


class TicketGraphState(TypedDict):
    ticket: Ticket
    run_id: int | None
    enabled: SolverEnabled
    targets: PipelineTargets | None
    triage: TriageResult | None
    dossier: dict[str, SearchHit]
    resolution: ResolutionResult | None
    valid_refs: list[str]
    tier: str
    routing_reason: str


class TicketGraphNode(Protocol):
    def __call__(self, state: TicketGraphState) -> Awaitable[dict[str, Any]]: ...


SOLVER_STAGE_IDS = ("triage", "investigate", "resolve", "answer", "escalate")
SOLVER_OPTIONAL_STAGES = frozenset(SolverEnabled.model_fields)
SOLVER_DIRECT_EDGES = (("triage", "investigate"),)
SOLVER_INVESTIGATION_ROUTES: dict[Hashable, str] = {
    "ready": "resolve",
    "empty": "escalate_empty",
    "disabled": "escalate_disabled",
}
SOLVER_RESOLUTION_ROUTES: dict[Hashable, str] = {
    "answer": "answer",
    "invalid_refs": "escalate_invalid_refs",
    "escalate": "escalate_model",
}


def solver_public_edges() -> list[tuple[str, str]]:
    routes = (
        *SOLVER_DIRECT_EDGES,
        *(("investigate", target) for target in SOLVER_INVESTIGATION_ROUTES.values()),
        *(("resolve", target) for target in SOLVER_RESOLUTION_ROUTES.values()),
    )
    return list(
        dict.fromkeys(
            (source, target if target in SOLVER_STAGE_IDS else "escalate")
            for source, target in routes
        )
    )


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

    async def ticket_runs(self, ticket_id: int) -> list[TicketRun]:
        return await self._tickets.list_runs(ticket_id)

    async def run(self, ticket_id: int, profile: SolverProfile | None = None) -> Ticket:
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
        run_id = None
        targets = None
        enabled = profile.enabled if profile is not None else SolverEnabled()
        if profile is None:
            started = await self._tickets.transition_status(ticket_id, previous_status, "running")
        else:
            targets, models = await self._profile_targets(profile)
            run_id = await self._tickets.start_run(ticket_id, previous_status, profile, models)
            started = run_id is not None
        if not started:
            raise TicketConflictError(f"ticket {ticket_id} changed before the run could start")
        try:
            await self._graph.ainvoke(
                {
                    "ticket": ticket,
                    "run_id": run_id,
                    "enabled": enabled,
                    "targets": targets,
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
        except (TicketAgentUnavailableError, SourceNotFoundError) as exc:
            if run_id is None:
                await self._tickets.transition_status(ticket_id, "running", previous_status)
            else:
                await self._tickets.update_result(
                    ticket_id, "failed", escalate_reason=_run_error(exc), run_id=run_id
                )
            raise
        except Exception as exc:
            await self._tickets.update_result(
                ticket_id,
                "failed",
                escalate_reason=_run_error(exc) if run_id is not None else str(exc)[:500],
                run_id=run_id,
            )
            raise

    def _build_graph(self) -> Any:
        graph: StateGraph[TicketGraphState, None, TicketGraphState, TicketGraphState] = StateGraph(
            TicketGraphState
        )
        graph.add_node("resolve_models", self._graph_resolve_models)
        graph.add_node("triage", self._trace_failure("triage", self._graph_triage))
        graph.add_node("investigate", self._trace_failure("investigate", self._graph_investigate))
        graph.add_node("resolve", self._trace_failure("resolve", self._graph_resolve))
        graph.add_node("answer", self._trace_failure("answer", self._graph_answer))
        graph.add_node(
            "escalate_empty", self._trace_failure("escalate", self._graph_escalate_empty)
        )
        graph.add_node(
            "escalate_invalid_refs",
            self._trace_failure("escalate", self._graph_escalate_invalid_refs),
        )
        graph.add_node(
            "escalate_model", self._trace_failure("escalate", self._graph_escalate_model)
        )
        graph.add_node(
            "escalate_disabled", self._trace_failure("escalate", self._graph_escalate_disabled)
        )
        graph.add_edge(START, "resolve_models")
        graph.add_edge("resolve_models", "triage")
        for source, target in SOLVER_DIRECT_EDGES:
            graph.add_edge(source, target)
        graph.add_conditional_edges(
            "investigate",
            self._route_after_investigation,
            SOLVER_INVESTIGATION_ROUTES,
        )
        graph.add_conditional_edges(
            "resolve",
            self._route_after_resolution,
            SOLVER_RESOLUTION_ROUTES,
        )
        for node in (
            "answer",
            "escalate_empty",
            "escalate_invalid_refs",
            "escalate_model",
            "escalate_disabled",
        ):
            graph.add_edge(node, END)
        return graph.compile()

    def _trace_failure(self, stage: str, action: TicketGraphNode) -> TicketGraphNode:
        async def run_stage(state: TicketGraphState) -> dict[str, Any]:
            started = time.monotonic()
            try:
                return await action(state)
            except Exception as exc:
                if state["run_id"] is not None:
                    inputs, model_id = self._failed_step_input(stage, state)
                    await self._tickets.add_step(
                        state["ticket"].id,
                        stage,
                        inputs,
                        {"reason": _run_error(exc), "error_type": type(exc).__name__},
                        model_id=model_id,
                        duration_ms=_elapsed_ms(started),
                        run_id=state["run_id"],
                        status="failed",
                    )
                raise

        return run_stage

    def _failed_step_input(
        self, stage: str, state: TicketGraphState
    ) -> tuple[dict[str, Any], int | None]:
        targets, triage = state["targets"], state["triage"]
        if stage == "triage" and targets is not None and targets.triage is not None:
            return {"query_origin": "ticket"}, targets.triage.model.id
        if stage == "resolve" and targets is not None and targets.strong is not None:
            _, refs = _format_dossier(state["dossier"], self._config.max_context_characters)
            return {"fragments": refs}, resolver_target(triage, targets).model.id
        if stage == "investigate":
            return {"query_origin": "triage" if triage is not None else "ticket"}, None
        if stage in {"answer", "escalate"}:
            return {"refs": list(state["dossier"])}, None
        return {}, None

    async def _graph_resolve_models(self, state: TicketGraphState) -> dict[str, Any]:
        targets = state["targets"]
        return {"targets": targets or await self._resolve_models(state["ticket"].source_id)}

    async def _graph_triage(self, state: TicketGraphState) -> dict[str, Any]:
        if not state["enabled"].triage:
            await self._tickets.add_step(
                state["ticket"].id,
                "triage",
                {},
                {"reason": "disabled_by_profile"},
                model_id=None,
                duration_ms=0,
                run_id=state["run_id"],
                status="skipped",
            )
            return {}
        targets = state["targets"]
        if targets is None or targets.triage is None:
            raise RuntimeError("ticket graph has no model targets")
        return {"triage": await self._run_triage(state["ticket"], targets.triage, state["run_id"])}

    async def _graph_investigate(self, state: TicketGraphState) -> dict[str, Any]:
        triage = state["triage"]
        ticket = state["ticket"]
        queries = (
            triage.search_queries
            if triage is not None
            else [f"{ticket.title}\n{ticket.description}".strip()]
        )
        dossier = await self._build_dossier(
            ticket.id, ticket.source_id, queries, state["run_id"], direct_query=triage is None
        )
        return {"dossier": dossier}

    @staticmethod
    def _route_after_investigation(state: TicketGraphState) -> str:
        if not state["dossier"]:
            return "empty"
        return "ready" if state["enabled"].resolve else "disabled"

    async def _graph_resolve(self, state: TicketGraphState) -> dict[str, Any]:
        targets, triage = state["targets"], state["triage"]
        if targets is None:
            raise RuntimeError("ticket graph is missing resolver inputs")
        resolver = resolver_target(triage, targets)
        tier = "cheap" if resolver is targets.cheap else "strong"
        routing_reason = (
            "simple ticket routed to the configured low-cost model"
            if tier == "cheap"
            else "standard or hard ticket routed to the strong model"
            if triage is not None and triage.complexity != "simple"
            else "no low-cost model is configured; using the strong model"
        )
        if triage is None:
            routing_reason = "triage is disabled; using the strong model"
        resolution = await self._run_resolver(
            state["ticket"],
            resolver,
            state["dossier"],
            triage,
            tier=tier,
            routing_reason=routing_reason,
            run_id=state["run_id"],
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
        if resolution is None:
            raise RuntimeError("ticket graph cannot finalize an incomplete answer")
        dossier = state["dossier"]
        if state["run_id"] is not None:
            await self._tickets.add_step(
                state["ticket"].id,
                "answer",
                {},
                {"refs": state["valid_refs"], "evidence": _evidence_map(dossier)},
                model_id=None,
                duration_ms=0,
                run_id=state["run_id"],
            )
        await self._tickets.update_result(
            state["ticket"].id,
            "answered",
            triage=triage.model_dump() if triage is not None else None,
            answer=resolution.answer,
            citations=[_citation(dossier[ref]) for ref in state["valid_refs"]],
            run_id=state["run_id"],
        )
        return {}

    async def _graph_escalate_empty(self, state: TicketGraphState) -> dict[str, Any]:
        triage = state["triage"]
        await self._escalate(
            state["ticket"].id,
            "в индексах проекта нет релевантного контента по обращению",
            triage,
            state["dossier"],
            skipped_llm=True,
            run_id=state["run_id"],
        )
        return {}

    async def _graph_escalate_invalid_refs(self, state: TicketGraphState) -> dict[str, Any]:
        triage = state["triage"]
        await self._escalate(
            state["ticket"].id,
            "модель не сослалась на найденные фрагменты контекста",
            triage,
            state["dossier"],
            run_id=state["run_id"],
        )
        return {}

    async def _graph_escalate_model(self, state: TicketGraphState) -> dict[str, Any]:
        triage, resolution = state["triage"], state["resolution"]
        if resolution is None:
            raise RuntimeError("ticket graph cannot escalate without a resolution result")
        await self._escalate(
            state["ticket"].id,
            resolution.escalate_reason or "недостаточно данных для ответа",
            triage,
            state["dossier"],
            run_id=state["run_id"],
        )
        return {}

    async def _graph_escalate_disabled(self, state: TicketGraphState) -> dict[str, Any]:
        await self._escalate(
            state["ticket"].id,
            "автоматическое решение отключено в профиле Solver",
            state["triage"],
            state["dossier"],
            skipped_llm=True,
            run_id=state["run_id"],
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

    async def _profile_targets(
        self, profile: SolverProfile
    ) -> tuple[PipelineTargets, SolverModelSnapshots]:
        models = profile.models
        needs_strong = profile.enabled.resolve or (
            profile.enabled.triage and models.ticket_triage is None
        )
        strong = (
            await self._target_for(
                models.ticket_resolution,
                fallback_error="select a chat model for the ticket pipeline before running it",
            )
            if needs_strong
            else None
        )
        triage = (
            await self._target_for(models.ticket_triage, fallback=strong)
            if profile.enabled.triage
            else None
        )
        cheap = (
            await self._target_for(models.ticket_resolution_cheap)
            if profile.enabled.resolve and profile.enabled.triage and models.ticket_resolution_cheap
            else None
        )
        resolver = strong if profile.enabled.resolve else None
        return PipelineTargets(triage, resolver, cheap), SolverModelSnapshots(
            ticket_resolution=_model_snapshot(resolver),
            ticket_triage=_model_snapshot(triage),
            ticket_resolution_cheap=_model_snapshot(cheap),
        )

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

    async def _run_triage(
        self, ticket: Ticket, target: ModelTarget, run_id: int | None = None
    ) -> TriageResult:
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
            run_id=run_id,
        )
        return triage

    async def _build_dossier(
        self,
        ticket_id: int,
        source_id: int,
        queries: list[str],
        run_id: int | None = None,
        *,
        direct_query: bool = False,
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
        if dossier or run_id is not None:
            await self._tickets.add_step(
                ticket_id,
                "investigate",
                {"query_origin": "ticket"} if direct_query else {"queries": queries},
                {
                    "refs": list(dossier),
                    "files": sorted({hit.path for hit in ordered}),
                    "fragments": len(ordered),
                },
                model_id=None,
                duration_ms=_elapsed_ms(started),
                run_id=run_id,
            )
        return dossier

    async def _run_resolver(
        self,
        ticket: Ticket,
        target: ModelTarget,
        dossier: dict[str, SearchHit],
        triage: TriageResult | None,
        tier: str,
        routing_reason: str,
        run_id: int | None = None,
    ) -> ResolutionResult:
        started = time.monotonic()
        evidence, visible_refs = _format_dossier(dossier, self._config.max_context_characters)
        prompt = (
            f"Ticket title: {ticket.title}\n\nTicket description:\n{ticket.description}\n\n"
            f"Triage summary: {triage.summary if triage is not None else 'unavailable'}\n\n"
            "Evidence fragments:\n" + evidence
        )
        resolution, usage = await _generate_parsed(
            self._gateway,
            target,
            RESOLVER_SYSTEM,
            prompt,
            ResolutionResult,
            self._config,
        )
        valid = _unique([ref for ref in resolution.source_refs if ref in visible_refs])
        routing = {
            "complexity": triage.complexity if triage is not None else None,
            "tier": tier,
            "reason": routing_reason,
        }
        await self._tickets.add_step(
            ticket.id,
            "resolve",
            {"fragments": visible_refs, "decision": resolution.decision},
            {**resolution.model_dump(), "source_refs": valid, "routing": routing},
            model_id=target.model.id,
            duration_ms=_elapsed_ms(started),
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
            cost_usd=step_cost_usd(target.pricing, usage.input_tokens, usage.output_tokens),
            run_id=run_id,
        )
        return resolution.model_copy(update={"source_refs": valid})

    async def _escalate(
        self,
        ticket_id: int,
        reason: str,
        triage: TriageResult | None,
        dossier: dict[str, SearchHit],
        skipped_llm: bool = False,
        run_id: int | None = None,
    ) -> Ticket:
        if skipped_llm:
            await self._tickets.add_step(
                ticket_id,
                "resolve",
                {"fragments": list(dossier)},
                {"decision": "escalate", "escalate_reason": reason, "skipped_llm": True},
                model_id=None,
                duration_ms=0,
                run_id=run_id,
                status="skipped",
            )
        if run_id is not None:
            await self._tickets.add_step(
                ticket_id,
                "escalate",
                {},
                {"reason": reason, "refs": list(dossier), "evidence": _evidence_map(dossier)},
                model_id=None,
                duration_ms=0,
                run_id=run_id,
            )
        updated = await self._tickets.update_result(
            ticket_id,
            "escalated",
            triage=triage.model_dump() if triage is not None else None,
            escalate_reason=reason,
            citations=[_citation(hit) for hit in dossier.values()],
            run_id=run_id,
        )
        assert updated is not None
        return updated


def _interleave_deduped(per_query_results: list[list[SearchHit]], limit: int) -> list[SearchHit]:
    seen: set[str] = set()
    ordered: list[SearchHit] = []
    for position in range(max((len(results) for results in per_query_results), default=0)):
        for results in per_query_results:
            if len(ordered) >= limit:
                return ordered
            if position >= len(results):
                continue
            hit = results[position]
            if hit.source_ref in seen:
                continue
            seen.add(hit.source_ref)
            ordered.append(hit)
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


def _evidence_map(dossier: dict[str, SearchHit]) -> dict[str, dict[str, Any]]:
    return {ref: _citation(hit) for ref, hit in dossier.items()}


def _model_snapshot(target: ModelTarget | None) -> SolverModelSnapshot | None:
    if target is None:
        return None
    return SolverModelSnapshot(id=target.model.id, display_name=target.model.display_name)


def _run_error(exc: Exception) -> str:
    if isinstance(exc, TicketAgentResponseError):
        return "The model returned a response that Solver could not read"
    if isinstance(exc, ProviderUnavailableError):
        return "The selected model provider is unavailable"
    if isinstance(exc, TimeoutError):
        return "The model request timed out"
    if isinstance(exc, TicketAgentUnavailableError):
        return "The configured model is unavailable"
    if isinstance(exc, SourceNotFoundError):
        return "The project is unavailable"
    return "Solver could not complete this step"


def _format_dossier(dossier: dict[str, SearchHit], max_characters: int) -> tuple[str, list[str]]:
    parts: list[str] = []
    visible: list[str] = []
    remaining = max_characters
    for ref, hit in dossier.items():
        location = hit.path + (
            f":{hit.start_line}-{hit.end_line}" if hit.start_line is not None else ""
        )
        header = f"[{ref}] {location}\n"
        available = remaining - len(header)
        if available <= 0:
            break
        fragment = header + hit.content[:available]
        parts.append(fragment)
        visible.append(ref)
        remaining -= len(fragment) + 2
    return "\n\n".join(parts), visible


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
            system_prompt,
            f"{user_prompt}\n\nThe previous response failed schema validation. "
            "Answer the original request using the supplied evidence and required JSON schema.\n"
            f"Previous response:\n{generated.text[:8000]}",
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


def resolver_target(triage: TriageResult | None, targets: "PipelineTargets") -> "ModelTarget":
    if triage is not None and targets.cheap is not None and triage.complexity == "simple":
        return targets.cheap
    if targets.strong is None:
        raise RuntimeError("ticket graph has no resolution model")
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
