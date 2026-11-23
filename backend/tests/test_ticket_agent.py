import json
from dataclasses import replace
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.diagnostic_tools import DiagnosticEvidence, DiagnosticTools
from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import (
    ProviderCredentials,
    ProviderUnavailableError,
    WorkspaceModelEntry,
)
from app.domain.repositories.material_generation import GeneratedJson
from app.domain.repositories.retrieval import (
    SearchHit,
    SearchMeta,
    SearchResponse,
    SearchUnavailableError,
)
from app.domain.solver import SolverEnabled, SolverModels, SolverModelSnapshots, SolverProfile
from app.domain.specialist_roles import (
    SPECIALIST_REGISTRY,
    SpecialistDefinition,
    register_specialist,
)
from app.domain.tickets import Ticket, TicketConflictError
from app.usecase.ticket_agent import (
    RESOLVER_SYSTEM,
    ModelTarget,
    PipelineTargets,
    ResolutionResult,
    TicketAgentConfig,
    TicketAgentResponseError,
    TicketAgentUnavailableError,
    TicketAgentUsecase,
    TriageResult,
    _format_dossier,
    _interleave_deduped,
    resolver_target,
    solver_optional_stages,
    solver_stage_ids,
)
from app.usecase.ticket_result_localization import LOCALIZATION_SYSTEM

CONFIG = TicketAgentConfig(
    timeout_seconds=5,
    max_output_tokens=512,
    context_chunks=6,
    max_context_characters=4000,
)

TRIAGE_JSON = json.dumps(
    {
        "category": "auth",
        "severity": "high",
        "complexity": "standard",
        "summary": "The user cannot sign in to the admin portal",
        "search_queries": ["вход в админку", "login admin handler"],
        "missing_info": ["Browser version"],
    },
    ensure_ascii=False,
)

ANSWER_JSON = json.dumps(
    {
        "decision": "answer",
        "answer": "Reset your password using the recovery form.",
        "escalate_reason": None,
        "source_refs": ["S1", "S9", "S1"],
    },
    ensure_ascii=False,
)

ESCALATE_JSON = json.dumps(
    {
        "decision": "escalate",
        "answer": None,
        "escalate_reason": "The indexes contain no information about this version.",
        "source_refs": [],
    },
    ensure_ascii=False,
)


class FakeTickets:
    def __init__(self) -> None:
        self.next_id = 1
        self.tickets: dict[int, Ticket] = {}
        self.steps: list[Any] = []
        self.run_models: SolverModelSnapshots | None = None
        self.unready_log_attachments = False

    async def create(self, source_id: int, title: str, description: str) -> Ticket:
        ticket = Ticket(
            id=self.next_id, source_id=source_id, title=title, description=description, status="new"
        )
        self.tickets[ticket.id] = ticket
        self.next_id += 1
        return ticket

    async def get(self, ticket_id: int) -> Ticket | None:
        return self.tickets.get(ticket_id)

    async def list_for_source(self, source_id: int) -> list[Ticket]:
        return [item for item in self.tickets.values() if item.source_id == source_id]

    async def transition_status(self, ticket_id: int, expected: str, status: str) -> bool:
        ticket = self.tickets[ticket_id]
        if ticket.status != expected:
            return False
        ticket.status = status
        return True

    async def start_run(
        self,
        ticket: Ticket,
        profile: SolverProfile,
        models: SolverModelSnapshots,
        rerun_context: Any,
    ) -> int | None:
        if await self.transition_status(ticket.id, ticket.status, "running"):
            self.run_models = models
            return 1
        return None

    async def update_result(self, ticket_id: int, status: str, **kwargs: Any) -> Ticket | None:
        ticket = self.tickets[ticket_id]
        ticket.status = status
        ticket.triage = kwargs.get("triage", ticket.triage)
        ticket.answer = kwargs.get("answer")
        ticket.escalate_reason = kwargs.get("escalate_reason")
        ticket.citations = kwargs.get("citations")
        ticket.localized_result = kwargs.get("localized_result")
        ticket.english_result = kwargs.get("english_result")
        return ticket

    async def add_step(
        self,
        ticket_id: int,
        step: str,
        input_data: dict,
        output_data: dict,
        model_id: int | None,
        duration_ms: int,
        **usage: Any,
    ) -> Any:
        record = {
            "ticket_id": ticket_id,
            "step": step,
            "input": input_data,
            "output": output_data,
            "model_id": model_id,
            "duration_ms": duration_ms,
            **usage,
        }
        self.steps.append(record)
        return record

    async def list_steps(self, ticket_id: int) -> list[Any]:
        return [item for item in self.steps if item["ticket_id"] == ticket_id]

    async def has_unready_log_attachments(self, ticket_id: int) -> bool:
        return self.unready_log_attachments


class FakeModels:
    def __init__(self, selection: int | None = 1, selections: dict[str, int] | None = None) -> None:
        self.selections = (
            selections
            if selections is not None
            else ({"ticket_resolution": selection} if selection is not None else {})
        )

    async def get_project_selections(self, source_id: int) -> dict[str, int]:
        return self.selections

    async def get_model(self, model_id: int) -> WorkspaceModelEntry | None:
        if model_id not in {1, 2, 3}:
            return None
        return WorkspaceModelEntry(
            id=model_id,
            provider_connection_id=7,
            provider_model_id=f"model-{model_id}",
            display_name=f"Model {model_id}",
            capabilities=["chat"],
            status="available",
            metadata={"pricing": {"prompt": "0.000001", "completion": "0.000002"}},
        )

    async def get_credentials(self, connection_id: int) -> ProviderCredentials | None:
        return ProviderCredentials(
            id=connection_id,
            provider_type="zai",
            name="zai",
            base_url="https://api.z.ai/api/paas/v4",
            api_key="key",
        )


class FakeRetrieval:
    def __init__(
        self,
        hits: list[SearchHit] | None = None,
        fail: bool = False,
        log_hits: list[SearchHit] | None = None,
    ) -> None:
        self.hits = hits if hits is not None else [_hit(n) for n in range(4)]
        self.fail = fail
        self.log_hits = log_hits or []
        self.calls: list[str] = []

    async def search(
        self, source_id: int, query: str, index_types: Any, top_k: int
    ) -> SearchResponse:
        self.calls.append(query)
        if self.fail:
            raise SearchUnavailableError("no completed indexes to search")
        return SearchResponse(
            hits=list(self.hits[:top_k]),
            meta=SearchMeta(
                indexes_searched=["code"],
                top_k=top_k,
                candidate_k=top_k,
                rerank_applied=False,
                warnings=[],
                latency_ms=1.0,
            ),
        )

    async def search_ticket_logs(
        self, source_id: int, ticket_id: int, query: str, top_k: int
    ) -> SearchResponse:
        return SearchResponse(
            hits=list(self.log_hits[:top_k]),
            meta=SearchMeta(
                indexes_searched=["ticket-log"],
                top_k=top_k,
                candidate_k=top_k,
                rerank_applied=False,
                warnings=[],
                latency_ms=1.0,
            ),
        )

    async def search_ticket_context(
        self, source_id: int, ticket_id: int, query: str, top_k: int
    ) -> SearchResponse:
        try:
            project = await self.search(source_id, query, None, top_k)
        except SearchUnavailableError:
            project = SearchResponse(
                hits=[],
                meta=SearchMeta([], top_k, top_k, False, [], 1.0),
            )
        logs = await self.search_ticket_logs(source_id, ticket_id, query, top_k)
        return SearchResponse(
            hits=[*project.hits, *logs.hits][:top_k],
            meta=project.meta,
        )


class FakeGateway:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []
        self.prompts: list[str] = []
        self.system_prompts: list[str] = []
        self.translation_requests: list[dict[str, Any]] = []
        self.translation_failure: str | None = None
        self.model_ids: list[str] = []
        self.usages: list[tuple[int | None, int | None]] = []

    def generate_json(
        self,
        credentials: ProviderCredentials,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        timeout: int,
        max_output_tokens: int,
    ) -> str:
        self.calls.append(system_prompt[:24])
        self.prompts.append(user_prompt)
        self.system_prompts.append(system_prompt)
        if not self.responses:
            raise AssertionError("unexpected extra LLM call")
        return self.responses.pop(0)

    def generate_json_with_usage(self, *args: Any, **kwargs: Any) -> GeneratedJson:
        if args[2] == LOCALIZATION_SYSTEM:
            request = json.loads(args[3])
            self.translation_requests.append(request)
            if self.translation_failure == "provider":
                raise ProviderUnavailableError("translation service unavailable")
            canonical = request["text"]
            translations = {
                "Reset your password using the recovery form.": (
                    "Сбросьте пароль через форму восстановления.",
                    "请通过恢复表单重置密码。",
                ),
                "The indexes contain no information about this version.": (
                    "В индексах нет сведений об этой версии.",
                    "项目索引中没有此版本的信息。",
                ),
            }
            ru, zh = translations.get(canonical, (f"Результат: {canonical}", f"结果：{canonical}"))
            return GeneratedJson(
                text=(
                    "invalid"
                    if self.translation_failure == "invalid"
                    else json.dumps({"original_language": "en", "en": None, "ru": ru, "zh": zh})
                ),
                input_tokens=23,
                output_tokens=49,
            )
        result = self.generate_json(*args, **kwargs)
        self.model_ids.append(str(args[1]))
        input_tokens, output_tokens = self.usages.pop(0) if self.usages else (None, None)
        return GeneratedJson(text=result, input_tokens=input_tokens, output_tokens=output_tokens)

    def embed_queries(self, *args: Any, **kwargs: Any) -> list[list[float]]:
        raise AssertionError("embeddings are not used by the ticket pipeline")


def _hit(n: int) -> SearchHit:
    return SearchHit(
        index_type="code",
        run_id=11,
        path=f"app/module_{n}.py",
        branch="",
        start_line=10 + n,
        end_line=20 + n,
        symbol=f"handler_{n}",
        content=f"def handler_{n}(): ...",
        score=0.5,
    )


def _usecase(
    tickets: FakeTickets,
    gateway: FakeGateway,
    retrieval: FakeRetrieval | None = None,
    models: FakeModels | None = None,
    sources_exists: bool = True,
    diagnostic_tools: DiagnosticTools | None = None,
    config: TicketAgentConfig = CONFIG,
) -> TicketAgentUsecase:
    return TicketAgentUsecase(
        tickets=tickets,
        sources=_FakeSources(sources_exists),
        models=models or FakeModels(),
        retrieval=retrieval or FakeRetrieval(),
        gateway=gateway,
        config=config,
        diagnostic_tools=diagnostic_tools,
    )


class _FakeSources:
    def __init__(self, exists: bool) -> None:
        self.exists = exists

    async def get_any(self, source_id: int) -> dict[str, Any] | None:
        return {"id": source_id} if self.exists else None


async def test_create_and_list_tickets() -> None:
    tickets = FakeTickets()
    usecase = _usecase(tickets, FakeGateway([]))
    created = await usecase.create_ticket(1, "Ошибка", "Описание ошибки")
    assert created.status == "new"
    listed = await usecase.list_tickets(1)
    assert [item.id for item in listed] == [created.id]


async def test_create_ticket_unknown_project() -> None:
    usecase = _usecase(FakeTickets(), FakeGateway([]), sources_exists=False)
    with pytest.raises(SourceNotFoundError):
        await usecase.create_ticket(1, "t", "d")


def test_ticket_agent_uses_compiled_langgraph_with_explicit_routes() -> None:
    usecase = _usecase(FakeTickets(), FakeGateway([]))

    graph = usecase._graph.get_graph()

    assert {"resolve_models", "triage", "investigate", "resolve", "answer"}.issubset(graph.nodes)
    assert {"escalate_empty", "escalate_invalid_refs", "escalate_model"}.issubset(graph.nodes)


def test_triage_accepts_typed_specialist_recommendations() -> None:
    triage = TriageResult.model_validate(
        {**json.loads(TRIAGE_JSON), "specialists": ["code", "logs"]}
    )
    assert triage.specialists == ["code", "logs"]
    assert TriageResult.model_validate_json(TRIAGE_JSON).specialists == []


async def test_registered_specialist_can_be_enabled_and_routed_without_graph_changes() -> None:
    role = "configuration"
    with pytest.raises(ValidationError, match="Unknown Solver role"):
        SolverEnabled.model_validate({role: True})
    register_specialist(
        role, SpecialistDefinition(frozenset({"configuration"}), "Check configuration.")
    )
    try:
        with pytest.raises(ValidationError):
            SolverEnabled.model_validate({role: "true"})
        enabled = SolverEnabled.model_validate({role: True})
        assert SolverEnabled.model_validate_json(enabled.model_dump_json()).specialist_enabled(role)
        assert role in solver_stage_ids() and role in solver_optional_stages()
        tickets = FakeTickets()
        triage = json.dumps({**json.loads(TRIAGE_JSON), "specialists": [role]})
        finding = json.dumps(
            {"status": "supported", "finding": "Configuration is documented", "source_refs": ["S1"]}
        )
        gateway = FakeGateway([triage, finding, ANSWER_JSON])
        usecase = _usecase(
            tickets,
            gateway,
            retrieval=FakeRetrieval(hits=[replace(_hit(1), index_type="configuration")]),
        )
        ticket = await usecase.create_ticket(1, "Ошибка", "Параметры конфигурации")
        profile = SolverProfile(
            id=1, name="Специалист", enabled=enabled, models=SolverModels(ticket_resolution=1)
        )
        result = await usecase.run(ticket.id, profile)
        assert result.status == "answered"
        assert role in [step["step"] for step in tickets.steps]
    finally:
        SPECIALIST_REGISTRY.pop(role)


async def test_documentation_ticket_uses_short_route_even_in_augmented_profile() -> None:
    tickets = FakeTickets()
    triage = json.dumps(
        {**json.loads(TRIAGE_JSON), "complexity": "simple", "specialists": ["code"]}
    )
    gateway = FakeGateway([triage, ANSWER_JSON])
    retrieval = FakeRetrieval(hits=[replace(_hit(1), index_type="documentation")])
    usecase = _usecase(tickets, gateway, retrieval=retrieval)
    ticket = await usecase.create_ticket(1, "Инструкция", "Как восстановить пароль?")
    profile = SolverProfile(
        id=1,
        name="Расширенный",
        enabled=SolverEnabled(code=True, review=True),
        models=SolverModels(ticket_resolution=1, ticket_resolution_cheap=2),
    )

    result = await usecase.run(ticket.id, profile)

    assert result.status == "answered"
    assert [step["step"] for step in tickets.steps] == [
        "triage",
        "investigate",
        "resolve",
        "answer",
    ]
    assert gateway.model_ids == ["model-1", "model-2"]


async def test_disputed_code_finding_runs_one_followup_and_independent_review() -> None:
    class FollowupRetrieval(FakeRetrieval):
        async def search(
            self, source_id: int, query: str, index_types: Any, top_k: int
        ) -> SearchResponse:
            response = await super().search(source_id, query, index_types, top_k)
            if query == "admin guard implementation":
                assert index_types == ["code"]
                return SearchResponse(hits=[_hit(7)], meta=response.meta)
            return response

    tickets = FakeTickets()
    triage = json.dumps({**json.loads(TRIAGE_JSON), "specialists": ["code"]})
    suggest = json.dumps(
        {
            "status": "gap",
            "finding": "Need guard implementation",
            "follow_up_query": "admin guard implementation",
        }
    )
    finding = json.dumps(
        {
            "status": "disputed",
            "finding": "Could be caused by the guard",
            "source_refs": ["S2", "S999"],
            "follow_up_query": "ignored",
        }
    )
    review = json.dumps(
        {"approved": False, "reason": "Evidence does not confirm the cause", "source_refs": ["S1"]}
    )
    gateway = FakeGateway([triage, suggest, finding, ANSWER_JSON, review])
    retrieval = FollowupRetrieval(hits=[replace(_hit(1), content="initial code evidence " * 1000)])
    usecase = _usecase(tickets, gateway, retrieval=retrieval)
    ticket = await usecase.create_ticket(1, "Ошибка авторизации", "У администратора возникает 401")
    profile = SolverProfile(
        id=1,
        name="Диагностика",
        enabled=SolverEnabled(code=True, review=True),
        models=SolverModels(ticket_resolution=1, ticket_resolution_cheap=2, ticket_triage=3),
    )

    result = await usecase.run(ticket.id, profile)

    assert result.status == "escalated"
    assert gateway.model_ids == ["model-3", "model-2", "model-2", "model-1", "model-3"]
    assert retrieval.calls.count("admin guard implementation") == 1
    assert "ignored" not in retrieval.calls
    assert [step["step"] for step in tickets.steps] == [
        "triage",
        "investigate",
        "code",
        "resolve",
        "review",
        "escalate",
    ]
    assert tickets.steps[2]["output"]["source_refs"] == ["S2"]
    assert tickets.steps[2]["input"]["refs"][0] == "S2"
    assert tickets.steps[2]["output"]["targeted_search"] == "completed"
    assert tickets.steps[-1]["output"]["evidence"]["S2"]["path"] == "app/module_7.py"


async def test_targeted_search_unavailable_is_distinguished_in_specialist_trace() -> None:
    class UnavailableSearch(FakeRetrieval):
        async def search(
            self, source_id: int, query: str, index_types: Any, top_k: int
        ) -> SearchResponse:
            if index_types == ["code"]:
                raise SearchUnavailableError("private backend details")
            return await super().search(source_id, query, index_types, top_k)

    tickets = FakeTickets()
    triage = json.dumps({**json.loads(TRIAGE_JSON), "specialists": ["code"]})
    gap = json.dumps(
        {"status": "gap", "finding": "Need the implementation", "follow_up_query": "admin guard"}
    )
    usecase = _usecase(
        tickets, FakeGateway([triage, gap, ANSWER_JSON]), retrieval=UnavailableSearch()
    )
    ticket = await usecase.create_ticket(1, "Ошибка", "Проблема доступа")
    profile = SolverProfile(
        id=1,
        name="Диагностика",
        enabled=SolverEnabled(code=True),
        models=SolverModels(ticket_resolution=1),
    )

    result = await usecase.run(ticket.id, profile)

    assert result.status == "answered"
    code_step = next(step for step in tickets.steps if step["step"] == "code")
    assert code_step["output"]["targeted_search"] == "unavailable"
    assert "private backend details" not in str(code_step)


class FakeDiagnosticTools:
    def __init__(self, ui: DiagnosticEvidence, web: DiagnosticEvidence) -> None:
        self.ui = ui
        self.web = web
        self.calls: list[tuple[str, int, int]] = []

    async def observe_ui(self, source_id: int, ticket_id: int) -> DiagnosticEvidence:
        self.calls.append(("ui", source_id, ticket_id))
        return self.ui

    async def search_web(self, source_id: int, ticket_id: int) -> DiagnosticEvidence:
        self.calls.append(("web", source_id, ticket_id))
        return self.web


@pytest.mark.parametrize(
    "observed, baseline, title",
    [
        (True, False, None),
        (False, True, None),
        (True, True, None),
        (True, False, "Не отображается галка"),
        (True, False, "复选框是否勾选？"),
    ],
)
async def test_ui_diagnostics_requires_observation_for_current_visibility(
    observed: bool, baseline: bool, title: str | None
) -> None:
    class UnavailableRetrieval(FakeRetrieval):
        async def search_ticket_context(
            self, source_id: int, ticket_id: int, query: str, top_k: int
        ) -> SearchResponse:
            raise ProviderUnavailableError("unavailable test input")

    ui_hit = replace(
        _hit(8),
        index_type="ui_observation",
        path="engineer-observation",
        branch="engineer",
        event_timestamp="2026-11-23T00:00:00Z",
        content=json.dumps(
            {
                "role": "button",
                "name": "Save",
                "width": 64,
                "height": 24,
                "visible": True,
                "enabled": True,
                "checked": None,
                "origin": "engineer",
                "observed_at": "2026-11-23T00:00:00Z",
            }
        ),
    )
    tools = FakeDiagnosticTools(
        DiagnosticEvidence("completed", [ui_hit], "Engineer observation")
        if observed
        else DiagnosticEvidence("skipped", [], "No observation"),
        DiagnosticEvidence("skipped", [], "Not enabled"),
    )
    tickets = FakeTickets()
    triage = json.dumps({**json.loads(TRIAGE_JSON), "specialists": ["ui"]})
    observation_ref = "S2" if baseline else "S1"
    answer = json.dumps({**json.loads(ANSWER_JSON), "source_refs": [observation_ref]})
    responses = [triage] if title is None else []
    if observed:
        responses.append(answer)
    gateway = FakeGateway(responses)
    usecase = _usecase(
        tickets,
        gateway,
        retrieval=UnavailableRetrieval()
        if title is not None
        else FakeRetrieval(
            hits=[replace(_hit(1), content="very long baseline " * 100)] if baseline else []
        ),
        diagnostic_tools=tools,
        config=replace(CONFIG, max_context_characters=420),
    )
    ticket = await usecase.create_ticket(9, title or "Наблюдение", "В чём причина несоответствия?")
    profile = SolverProfile(
        id=1,
        name="Диагностика",
        enabled=SolverEnabled(triage=title is None, ui=True),
        models=SolverModels(ticket_resolution=1),
    )

    result = await usecase.run(ticket.id, profile)

    assert tools.calls == [("ui", 9, ticket.id)]
    investigation = next(step for step in tickets.steps if step["step"] == "investigate")
    assert investigation["output"]["search_status"] == (
        "unavailable" if title is not None else "completed" if baseline else "empty"
    )
    if observed:
        assert result.status == "answered"
        assert result.citations and result.citations[0]["index_type"] == "ui_observation"
        observed_data = next(step for step in tickets.steps if step["step"] == "ui")["output"][
            "observations"
        ][observation_ref]
        assert (
            next(step for step in tickets.steps if step["step"] == "resolve")["input"]["fragments"][
                0
            ]
            == observation_ref
        )
        assert observed_data["width"] == 64
        assert observed_data["origin"] == "engineer"
        assert observed_data["observed_at"] == "2026-11-23T00:00:00Z"
    else:
        assert result.status == "escalated"
        assert result.citations and result.citations[0]["index_type"] == "code"
        assert (
            tickets.steps[-1]["output"]["reason"]
            == "The current state of the interface could not be confirmed by an observation."
        )


async def test_external_web_evidence_cannot_by_itself_confirm_answer() -> None:
    web_hit = replace(
        _hit(9),
        index_type="external_web",
        path="https://example.com/errors",
        branch="searxng",
        content=json.dumps({"title": "Help", "snippet": "This snippet should not be persisted"}),
    )
    tools = FakeDiagnosticTools(
        DiagnosticEvidence("skipped", [], "Not enabled"),
        DiagnosticEvidence("completed", [web_hit], "External source"),
    )
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON])
    usecase = _usecase(tickets, gateway, retrieval=FakeRetrieval(hits=[]), diagnostic_tools=tools)
    ticket = await usecase.create_ticket(4, "Ошибка", "Приложение остановилось")
    profile = SolverProfile(
        id=1,
        name="Внешние сведения",
        enabled=SolverEnabled(web=True),
        models=SolverModels(ticket_resolution=1),
    )

    result = await usecase.run(ticket.id, profile)

    assert tools.calls == [("web", 4, ticket.id)]
    assert result.status == "escalated"
    assert result.citations and result.citations[0]["index_type"] == "external_web"
    assert gateway.model_ids == ["model-1"]
    observed_data = next(step for step in tickets.steps if step["step"] == "web")["output"][
        "observations"
    ]["S1"]
    assert observed_data["url"] == "https://example.com/errors"
    assert observed_data["title"] == "Help"
    assert "snippet" not in observed_data


async def test_explicit_measurement_can_run_ui_with_simple_triage_and_docs() -> None:
    tools = FakeDiagnosticTools(
        DiagnosticEvidence("skipped", [], "No observation"),
        DiagnosticEvidence("skipped", [], "Not enabled"),
    )
    tickets = FakeTickets()
    triage = json.dumps({**json.loads(TRIAGE_JSON), "complexity": "simple"})
    gateway = FakeGateway([triage])
    usecase = _usecase(
        tickets,
        gateway,
        retrieval=FakeRetrieval(hits=[replace(_hit(1), index_type="documentation")]),
        diagnostic_tools=tools,
    )
    ticket = await usecase.create_ticket(4, "Ширина кнопки", "Сколько пикселей на экране?")
    profile = SolverProfile(
        id=1,
        name="Измерение",
        enabled=SolverEnabled(ui=True),
        models=SolverModels(ticket_resolution=1),
    )
    result = await usecase.run(ticket.id, profile)

    assert tools.calls == [("ui", 4, ticket.id)]
    assert result.status == "escalated"


async def test_answer_and_trace_keep_only_links_grounded_in_visible_citations() -> None:
    tickets = FakeTickets()
    valid = "https://example.com/guide"
    invented = "https://github.com/example/repo/blob/lab5/docs/user_talks.md"
    answer = json.dumps(
        {
            **json.loads(ANSWER_JSON),
            "answer": f"[Руководство]({valid}) и [lab5/docs/user_talks.md]({invented}). Вызовите `/api/v1/tickets`.",
        }
    )
    retrieval = FakeRetrieval(hits=[replace(_hit(1), content=f"Guide: {valid}")])
    usecase = _usecase(tickets, FakeGateway([TRIAGE_JSON, answer]), retrieval=retrieval)
    ticket = await usecase.create_ticket(1, "Ссылка на руководство", "Где посмотреть документацию?")

    result = await usecase.run(ticket.id)

    assert result.answer and f"[Руководство]({valid})" in result.answer
    assert invented not in result.answer and "lab5/docs/user_talks.md" not in result.answer
    assert "`/api/v1/tickets`" in result.answer
    assert tickets.steps[-1]["output"]["answer"] == result.answer


async def test_run_answers_with_valid_citations() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON, ANSWER_JSON])
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "Не пускает в админку", "401 на /admin")

    result = await usecase.run(ticket.id)

    assert result.status == "answered"
    assert result.answer is not None and "Reset your password" in result.answer
    assert result.triage is not None and result.triage["category"] == "auth"
    assert [item["path"] for item in (result.citations or [])] == ["app/module_0.py"]
    assert [item["label"] for item in (result.citations or [])] == ["S1"]
    assert [step["step"] for step in tickets.steps] == ["triage", "investigate", "resolve"]
    assert tickets.steps[-1]["output"]["routing"]["tier"] == "strong"
    assert tickets.steps[-1]["tokens_in"] is None
    assert len(gateway.calls) == 2


async def test_solver_profile_without_resolution_returns_evidence_to_engineer() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([])
    retrieval = FakeRetrieval()
    usecase = _usecase(tickets, gateway, retrieval=retrieval)
    ticket = await usecase.create_ticket(1, "Ошибка загрузки", "HTTP 502 при сохранении")
    profile = SolverProfile(
        id=5,
        name="Ручная проверка",
        enabled=SolverEnabled(triage=False, resolve=False),
        models=SolverModels(),
    )

    result = await usecase.run(ticket.id, profile=profile)

    assert result.status == "escalated"
    assert result.citations
    assert retrieval.calls == ["Ошибка загрузки\nHTTP 502 при сохранении"]
    assert not gateway.calls
    assert [step["step"] for step in tickets.steps] == [
        "triage",
        "investigate",
        "resolve",
        "escalate",
    ]
    assert tickets.steps[0]["status"] == tickets.steps[2]["status"] == "skipped"
    assert tickets.steps[-1]["output"]["evidence"]["S1"]["path"] == "app/module_0.py"


async def test_solver_profile_without_triage_routes_to_strong_model() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([ANSWER_JSON])
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "Ошибка загрузки", "HTTP 502 при сохранении")
    profile = SolverProfile(
        id=5,
        name="Прямой поиск",
        enabled=SolverEnabled(triage=False, resolve=True),
        models=SolverModels(ticket_resolution=1, ticket_triage=2, ticket_resolution_cheap=3),
    )

    result = await usecase.run(ticket.id, profile=profile)

    assert result.status == "answered"
    assert [citation["path"] for citation in result.citations or []] == ["app/module_0.py"]
    assert gateway.model_ids == ["model-1"]
    assert tickets.steps[1]["input"] == {"query_origin": "ticket"}
    assert tickets.run_models is not None
    assert tickets.run_models.ticket_triage is None
    assert tickets.run_models.ticket_resolution_cheap is None
    terminal = tickets.steps[-1]["output"]
    assert terminal["refs"] == ["S1"]
    assert terminal["evidence"]["S1"]["start_line"] == 10
    assert terminal["evidence"]["S2"]["start_line"] == 11


async def test_solver_profile_snapshots_inherited_triage_model_when_dossier_is_empty() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON])
    usecase = _usecase(tickets, gateway, retrieval=FakeRetrieval(hits=[]))
    ticket = await usecase.create_ticket(1, "Ошибка", "Описание ошибки")
    profile = SolverProfile(
        id=5,
        name="Автоматически",
        enabled=SolverEnabled(),
        models=SolverModels(ticket_resolution=1),
    )

    result = await usecase.run(ticket.id, profile=profile)

    assert result.status == "escalated"
    assert gateway.model_ids == ["model-1"]
    assert tickets.run_models is not None
    assert tickets.run_models.model_dump()["ticket_triage"] == {"id": 1, "display_name": "Model 1"}
    assert tickets.steps[2]["step"] == "resolve"
    assert tickets.steps[2]["status"] == "skipped"
    assert tickets.steps[-1]["output"]["evidence"] == {}


async def test_solver_failure_trace_records_model_and_refs_without_provider_payload() -> None:
    class FailingGateway(FakeGateway):
        def generate_json(self, *args: Any, **kwargs: Any) -> str:
            raise TimeoutError("provider request contained sensitive data")

    tickets = FakeTickets()
    usecase = _usecase(tickets, FailingGateway([]))
    ticket = await usecase.create_ticket(1, "Ошибка", "Описание ошибки")
    profile = SolverProfile(
        id=6,
        name="Прямой поиск",
        enabled=SolverEnabled(triage=False),
        models=SolverModels(ticket_resolution=1),
    )

    with pytest.raises(TimeoutError):
        await usecase.run(ticket.id, profile=profile)

    failure = tickets.steps[-1]
    assert failure["step"] == "resolve"
    assert failure["status"] == "failed"
    assert failure["model_id"] == 1
    assert failure["input"]["fragments"] == ["S1", "S2", "S3", "S4"]
    assert failure["output"] == {
        "error_type": "TimeoutError",
        "reason": "The model request timed out",
    }
    assert ticket.escalate_reason == "The model request timed out"


def test_resolver_instructions_distinguish_operational_causes_and_normal_flows() -> None:
    assert "OOM-kill" in RESOLVER_SYSTEM
    assert "disk exhaustion" in RESOLVER_SYSTEM
    assert "expected user flow" in RESOLVER_SYSTEM
    assert "claim a code defect unless independent evidence supports it" in RESOLVER_SYSTEM


async def test_run_stops_before_models_when_log_attachment_is_not_ready() -> None:
    tickets = FakeTickets()
    tickets.unready_log_attachments = True
    gateway = FakeGateway([TRIAGE_JSON, ANSWER_JSON])
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "OOM", "Worker stopped unexpectedly")

    with pytest.raises(TicketConflictError, match="log archive"):
        await usecase.run(ticket.id)

    assert ticket.status == "new"
    assert gateway.calls == []


async def test_run_includes_current_ticket_logs_as_scoped_citations() -> None:
    tickets = FakeTickets()
    retrieval = FakeRetrieval(hits=[])
    gateway = FakeGateway([TRIAGE_JSON, ANSWER_JSON])
    usecase = _usecase(tickets, gateway, retrieval=retrieval)
    ticket = await usecase.create_ticket(1, "OOM", "Worker stopped unexpectedly")
    retrieval.log_hits = [
        SearchHit(
            index_type="ticket-log",
            run_id=0,
            path="logs/server.log",
            branch="",
            start_line=17,
            end_line=22,
            symbol=None,
            content="OOM killer terminated worker",
            score=0.02,
            ticket_id=ticket.id,
            attachment_id=9,
            event_timestamp="2026-11-17T01:02:03Z",
        )
    ]

    result = await usecase.run(ticket.id)

    assert result.status == "answered"
    assert result.citations is not None
    assert result.citations[0]["source_ref"].startswith(f"ticket:{ticket.id}:attachment:9:")
    assert result.citations[0]["event_timestamp"] == "2026-11-17T01:02:03Z"


async def test_simple_ticket_uses_cheap_model_and_records_usage_and_cost() -> None:
    tickets = FakeTickets()
    triage = json.loads(TRIAGE_JSON)
    triage["complexity"] = "simple"
    gateway = FakeGateway([json.dumps(triage, ensure_ascii=False), ANSWER_JSON])
    gateway.usages = [(100, 10), (200, 20)]
    models = FakeModels(
        selections={
            "ticket_resolution": 1,
            "ticket_triage": 3,
            "ticket_resolution_cheap": 2,
        }
    )
    usecase = _usecase(tickets, gateway, models=models)
    ticket = await usecase.create_ticket(1, "Простой вопрос", "Как восстановить доступ?")

    await usecase.run(ticket.id)

    assert gateway.model_ids == ["model-3", "model-2"]
    triage_step = tickets.steps[0]
    resolve_step = tickets.steps[-1]
    assert (triage_step["tokens_in"], triage_step["tokens_out"]) == (100, 10)
    assert triage_step["cost_usd"] == pytest.approx(0.00012)
    assert (resolve_step["tokens_in"], resolve_step["tokens_out"]) == (200, 20)
    assert resolve_step["cost_usd"] == pytest.approx(0.00024)
    assert resolve_step["output"]["routing"]["tier"] == "cheap"


async def test_run_escalates_when_resolver_decides() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON, ESCALATE_JSON])
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "Странный баг", "описание")

    result = await usecase.run(ticket.id)

    assert result.status == "escalated"
    assert "indexes contain no information" in (result.escalate_reason or "")
    assert result.localized_result is not None
    assert result.localized_result.en == result.escalate_reason
    assert "сведений об этой версии" in result.localized_result.ru
    assert "此版本" in result.localized_result.zh
    assert result.answer is None


async def test_run_escalates_without_llm_when_dossier_empty() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON])
    usecase = _usecase(tickets, gateway, retrieval=FakeRetrieval(hits=[]))
    ticket = await usecase.create_ticket(1, "t", "d")

    result = await usecase.run(ticket.id)

    assert result.status == "escalated"
    assert "no content relevant" in (result.escalate_reason or "")
    assert len(gateway.calls) == 1
    resolve_steps = [s for s in tickets.steps if s["step"] == "resolve"]
    assert resolve_steps and resolve_steps[0]["output"].get("skipped_llm") is True


async def test_run_escalates_when_search_unavailable() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON])
    usecase = _usecase(tickets, gateway, retrieval=FakeRetrieval(fail=True))
    ticket = await usecase.create_ticket(1, "t", "d")

    result = await usecase.run(ticket.id)

    assert result.status == "escalated"


async def test_run_escalates_when_refs_invalid() -> None:
    bad = json.dumps(
        {
            "decision": "answer",
            "answer": "Вот ответ.",
            "escalate_reason": None,
            "source_refs": ["S99"],
        },
        ensure_ascii=False,
    )
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON, bad])
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "t", "d")

    result = await usecase.run(ticket.id)

    assert result.status == "escalated"
    assert "did not cite" in (result.escalate_reason or "")


def test_deduplication_continues_past_a_fully_repeated_rank() -> None:
    a, b, c = (_hit(n) for n in range(3))
    assert _interleave_deduped([[a, b, c], [b, a]], 3) == [a, b, c]


async def test_run_conflict_while_running() -> None:
    tickets = FakeTickets()
    usecase = _usecase(tickets, FakeGateway([]))
    ticket = await usecase.create_ticket(1, "t", "d")
    ticket.status = "running"
    with pytest.raises(TicketConflictError):
        await usecase.run(ticket.id)


async def test_run_without_model_restores_status() -> None:
    tickets = FakeTickets()
    usecase = _usecase(tickets, FakeGateway([]), models=FakeModels(selection=None))
    ticket = await usecase.create_ticket(1, "t", "d")

    with pytest.raises(TicketAgentUnavailableError):
        await usecase.run(ticket.id)

    assert tickets.tickets[ticket.id].status == "new"
    assert tickets.steps == []


async def test_rerun_without_model_preserves_previous_answer_and_sources() -> None:
    tickets = FakeTickets()
    usecase = _usecase(tickets, FakeGateway([]), models=FakeModels(selection=None))
    ticket = await usecase.create_ticket(1, "t", "d")
    await tickets.update_result(ticket.id, "answered", answer="Saved", citations=[{"path": "a.py"}])

    with pytest.raises(TicketAgentUnavailableError):
        await usecase.run(ticket.id)

    assert ticket.status == "answered"
    assert ticket.answer == "Saved"
    assert ticket.citations == [{"path": "a.py"}]


async def test_run_provider_failure_marks_failed() -> None:
    class FailingGateway(FakeGateway):
        def generate_json(self, *args: Any, **kwargs: Any) -> str:
            raise RuntimeError("provider down")

    tickets = FakeTickets()
    usecase = _usecase(tickets, FailingGateway([]))
    ticket = await usecase.create_ticket(1, "t", "d")

    with pytest.raises(RuntimeError):
        await usecase.run(ticket.id)

    assert tickets.tickets[ticket.id].status == "failed"


async def test_repair_retry_recovers_invalid_json() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway(["not json at all", TRIAGE_JSON, ANSWER_JSON])
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "t", "d")

    result = await usecase.run(ticket.id)

    assert result.status == "answered"
    assert len(gateway.calls) == 3
    assert gateway.calls[0] == gateway.calls[1]


def test_dossier_counts_separators_and_truncates_oversized_first_source() -> None:
    text, visible = _format_dossier({"S1": _hit(1), "S2": _hit(2)}, 36)
    assert 0 < len(text) <= 36
    assert visible == ["S1"]


def test_bounded_dossier_keeps_prioritized_refs_and_room_for_older_evidence() -> None:
    dossier = {
        "S1": replace(_hit(1), content="original evidence"),
        "S2": replace(_hit(2), content="fresh evidence " * 100),
    }
    text, visible = _format_dossier(dossier, 190, priority=["S2"])
    assert visible == ["S2", "S1"]
    assert "fresh evidence" in text and "original evidence" in text
    assert len(text) <= 190


async def test_repair_usage_is_added_to_step_totals() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway(["not json", TRIAGE_JSON, ANSWER_JSON])
    gateway.usages = [(5, 3), (7, 4), (9, 2)]
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "Ошибка входа", "Не входит в систему")

    await usecase.run(ticket.id)

    assert tickets.steps[0]["tokens_in"] == 12
    assert tickets.steps[0]["tokens_out"] == 7
    assert tickets.steps[0]["cost_usd"] == pytest.approx(0.000026)


async def test_unrecoverable_json_fails_ticket() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway(["garbage", "still garbage"])
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "t", "d")

    with pytest.raises(TicketAgentResponseError):
        await usecase.run(ticket.id)

    assert tickets.tickets[ticket.id].status == "failed"


def test_contracts_validation() -> None:
    with pytest.raises(ValidationError):
        TriageResult.model_validate(
            {"category": "x", "severity": "low", "summary": "s", "search_queries": ["login"]}
        )
    with pytest.raises(ValidationError):
        TriageResult.model_validate(
            {
                "category": "x",
                "severity": "low",
                "complexity": "unknown",
                "summary": "s",
                "search_queries": ["login"],
            }
        )
    with pytest.raises(ValidationError):
        TriageResult.model_validate(
            {
                "category": "x",
                "severity": "ultra",
                "complexity": "standard",
                "summary": "s",
                "search_queries": ["login"],
            }
        )
    with pytest.raises(ValidationError):
        ResolutionResult.model_validate({"decision": "answer", "answer": "  ", "source_refs": []})
    resolution = ResolutionResult.model_validate(
        {"decision": "escalate", "escalate_reason": "мало данных"}
    )
    assert resolution.source_refs == []


def test_resolver_target_uses_cheap_only_for_simple_complexity() -> None:
    credentials = ProviderCredentials(
        id=1, provider_type="ollama", name="local", base_url="http://localhost", api_key=None
    )
    strong = ModelTarget(
        WorkspaceModelEntry(provider_model_id="strong", display_name="Strong", id=1),
        credentials,
        None,
    )
    cheap = ModelTarget(
        WorkspaceModelEntry(provider_model_id="cheap", display_name="Cheap", id=2),
        credentials,
        None,
    )
    targets = PipelineTargets(triage=strong, strong=strong, cheap=cheap)

    def triage(complexity: str) -> TriageResult:
        return TriageResult(
            category="auth",
            severity="low",
            complexity=complexity,
            summary="issue",
            search_queries=["login issue"],
        )

    assert resolver_target(triage("simple"), targets) is cheap
    assert resolver_target(triage("standard"), targets) is strong
    assert resolver_target(triage("hard"), targets) is strong
    assert (
        resolver_target(triage("simple"), PipelineTargets(triage=strong, strong=strong, cheap=None))
        is strong
    )


@pytest.mark.parametrize("comment", ["Still failing after reset", "   ", None])
async def test_rerun_supplies_previous_result_as_ticket_data(comment: str | None) -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON, ANSWER_JSON, TRIAGE_JSON, ANSWER_JSON])
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "Admin sign-in", "HTTP 401 from /admin")
    first = await usecase.run(ticket.id)
    assert first.answer
    previous_answer = first.answer
    await usecase.run(ticket.id, comment=comment)
    assert all("Previous run context" not in prompt for prompt in gateway.prompts[:2])
    assert all(previous_answer in prompt for prompt in gateway.prompts[2:])
    if comment and comment.strip():
        assert all(comment in prompt for prompt in gateway.prompts[2:])
    context = tickets.steps[-1]["input"]["rerun_context"]
    assert context["previous_result"]["answer"] == previous_answer
    assert context["comment"] == (comment.strip() or None if comment is not None else None)


async def test_deterministic_escalation_has_three_languages_without_translation_request() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON])
    usecase = _usecase(tickets, gateway, retrieval=FakeRetrieval(hits=[]))
    ticket = await usecase.create_ticket(1, "HTTP 503", "The upload is unavailable")

    result = await usecase.run(ticket.id)

    assert result.status == "escalated"
    assert result.localized_result is not None
    assert result.escalate_reason == result.localized_result.en
    assert "В индексах проекта" in result.localized_result.ru
    assert "索引" in result.localized_result.zh
    assert len(gateway.calls) == 1
    assert not gateway.translation_requests


@pytest.mark.parametrize("translation_failure", [None, "provider", "invalid"])
async def test_answer_is_localized_after_canonical_english_analysis(
    translation_failure: str | None,
) -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON, ANSWER_JSON])
    gateway.translation_failure = translation_failure
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "Ошибка входа", "登录失败 HTTP 401")
    profile = SolverProfile(
        id=5, name="Default", enabled=SolverEnabled(), models=SolverModels(ticket_resolution=1)
    )

    result = await usecase.run(ticket.id, profile=profile)

    assert result.status == "answered"
    assert result.answer == "Reset your password using the recovery form."
    assert result.english_result == result.answer
    assert all("English" in prompt for prompt in gateway.system_prompts)
    assert all("登录失败 HTTP 401" in prompt for prompt in gateway.prompts)
    assert gateway.translation_requests == [{"original_language": "en", "text": result.answer}]
    final_trace = tickets.steps[-1]
    assert final_trace["step"] == "answer"
    assert final_trace["model_id"] is not None
    if translation_failure:
        assert result.localized_result is None
        assert final_trace["output"]["localization_status"] == "failed"
        if translation_failure == "invalid":
            assert (final_trace["tokens_in"], final_trace["tokens_out"]) == (23, 49)
    else:
        assert result.localized_result is not None
        assert result.localized_result.en == result.answer
        assert result.localized_result.ru == "Сбросьте пароль через форму восстановления."
        assert result.localized_result.zh == "请通过恢复表单重置密码。"
        assert final_trace["output"]["localization_status"] == "completed"
        assert (final_trace["tokens_in"], final_trace["tokens_out"]) == (23, 49)
