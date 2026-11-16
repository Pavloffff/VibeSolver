import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import ProviderCredentials, WorkspaceModelEntry
from app.domain.repositories.material_generation import GeneratedJson
from app.domain.repositories.retrieval import (
    SearchHit,
    SearchMeta,
    SearchResponse,
    SearchUnavailableError,
)
from app.domain.tickets import Ticket, TicketConflictError
from app.usecase.ticket_agent import (
    ModelTarget,
    PipelineTargets,
    ResolutionResult,
    TicketAgentConfig,
    TicketAgentResponseError,
    TicketAgentUnavailableError,
    TicketAgentUsecase,
    TriageResult,
    resolver_target,
)

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
        "summary": "Пользователь не может войти в админку",
        "search_queries": ["вход в админку", "login admin handler"],
        "missing_info": ["версия браузера"],
    },
    ensure_ascii=False,
)

ANSWER_JSON = json.dumps(
    {
        "decision": "answer",
        "answer": "Сбросьте пароль через форму восстановления.",
        "escalate_reason": None,
        "source_refs": ["S1", "S9", "S1"],
    },
    ensure_ascii=False,
)

ESCALATE_JSON = json.dumps(
    {
        "decision": "escalate",
        "answer": None,
        "escalate_reason": "В индексах нет данных о этой версии.",
        "source_refs": [],
    },
    ensure_ascii=False,
)


class FakeTickets:
    def __init__(self) -> None:
        self.next_id = 1
        self.tickets: dict[int, Ticket] = {}
        self.steps: list[Any] = []

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

    async def update_result(self, ticket_id: int, status: str, **kwargs: Any) -> Ticket | None:
        ticket = self.tickets[ticket_id]
        ticket.status = status
        ticket.triage = kwargs.get("triage", ticket.triage)
        ticket.answer = kwargs.get("answer")
        ticket.escalate_reason = kwargs.get("escalate_reason")
        ticket.citations = kwargs.get("citations")
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
    def __init__(self, hits: list[SearchHit] | None = None, fail: bool = False) -> None:
        self.hits = hits if hits is not None else [_hit(n) for n in range(4)]
        self.fail = fail
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


class FakeGateway:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []
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
        if not self.responses:
            raise AssertionError("unexpected extra LLM call")
        return self.responses.pop(0)

    def generate_json_with_usage(self, *args: Any, **kwargs: Any) -> GeneratedJson:
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
) -> TicketAgentUsecase:
    return TicketAgentUsecase(
        tickets=tickets,
        sources=_FakeSources(sources_exists),
        models=models or FakeModels(),
        retrieval=retrieval or FakeRetrieval(),
        gateway=gateway,
        config=CONFIG,
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


async def test_run_answers_with_valid_citations() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON, ANSWER_JSON])
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "Не пускает в админку", "401 на /admin")

    result = await usecase.run(ticket.id)

    assert result.status == "answered"
    assert result.answer is not None and "Сбросьте" in result.answer
    assert result.triage is not None and result.triage["category"] == "auth"
    assert [item["path"] for item in (result.citations or [])] == ["app/module_0.py"]
    assert [step["step"] for step in tickets.steps] == ["triage", "investigate", "resolve"]
    assert tickets.steps[-1]["output"]["routing"]["tier"] == "strong"
    assert tickets.steps[-1]["tokens_in"] is None
    assert len(gateway.calls) == 2


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
    assert "индексах нет данных" in (result.escalate_reason or "")
    assert result.answer is None


async def test_run_escalates_without_llm_when_dossier_empty() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON])
    usecase = _usecase(tickets, gateway, retrieval=FakeRetrieval(hits=[]))
    ticket = await usecase.create_ticket(1, "t", "d")

    result = await usecase.run(ticket.id)

    assert result.status == "escalated"
    assert "нет релевантного контента" in (result.escalate_reason or "")
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
    assert "не сослалась" in (result.escalate_reason or "")


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
