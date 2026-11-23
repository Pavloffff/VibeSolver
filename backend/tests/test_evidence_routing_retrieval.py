import json
from dataclasses import replace
from unittest.mock import AsyncMock

from test_ticket_agent import (
    ANSWER_JSON,
    TRIAGE_JSON,
    FakeDiagnosticTools,
    FakeGateway,
    FakeRetrieval,
    FakeTickets,
    _hit,
    _usecase,
)

from app.domain.diagnostic_tools import DiagnosticEvidence, scoped_log_error_signatures
from app.domain.repositories.retrieval import SearchMeta, SearchResponse


async def test_dossier_preserves_seed_labels_and_adds_diverse_scoped_evidence() -> None:
    code = _hit(0)
    log = replace(_hit(1), index_type="ticket-log", ticket_id=1, attachment_id=24)
    flow = replace(_hit(2), index_type="user_flow")
    docs = replace(_hit(3), index_type="documentation")
    history = replace(_hit(4), index_type="ticket_history", ticket_id=8)
    retrieval = FakeRetrieval([code])
    retrieval.search_project_evidence = AsyncMock(
        return_value=SearchResponse(
            [flow, docs, code],
            SearchMeta(["user_flow", "documentation", "code"], 4, 16, False, [], 0),
        )
    )
    tickets = FakeTickets()
    tickets.search_answered_history = AsyncMock(return_value=[history])
    usecase = _usecase(tickets, FakeGateway([]), retrieval=retrieval)

    dossier = await usecase._build_dossier(
        1, 10, ["retry upload"], run_id=2, seed={"S9": log, "S1": code}, stage="recheck"
    )

    assert dossier["S9"] is log
    assert dossier["S1"] is code
    assert list(dossier.values()) == [log, code, flow, docs, history]
    assert list(dossier) == ["S9", "S1", "S10", "S11", "S12"]
    tickets.search_answered_history.assert_awaited_once_with(10, 1, ["retry upload"])
    assert tickets.steps[-1]["step"] == "recheck"
    assert tickets.steps[-1]["output"]["indexes_searched"] == [
        "user_flow",
        "documentation",
        "code",
        "ticket_history",
    ]


async def test_triage_accepts_bounded_evidence_without_a_new_model_call() -> None:
    tickets = FakeTickets()
    gateway = FakeGateway([TRIAGE_JSON])
    usecase = _usecase(tickets, gateway)
    ticket = await usecase.create_ticket(1, "Upload unavailable", "HTTP 503 from connector")
    target = await usecase._target_for(1, fallback_error="missing model")
    assert target is not None
    evidence = "[S1] Attached log observed app 2.4.2\n" + "unique-tail " * 1500

    await usecase._run_triage(ticket, target, evidence_context=evidence)

    assert len(gateway.prompts) == 1
    assert "[S1] Attached log observed app 2.4.2" in gateway.prompts[0]
    assert len(gateway.prompts[0]) < len(evidence)
    assert "untrusted" in gateway.system_prompts[0]


async def test_search_project_evidence_reads_documentation_first_and_embeds_once() -> None:
    from unittest.mock import Mock

    from test_retrieval_usecase import (
        FakeIndexing,
        FakeModels,
        FakeSearch,
        FakeSources,
        _run_status,
    )

    from app.usecase.retrieval import RetrievalUsecase

    statuses = [
        _run_status("code", "completed", 11),
        _run_status("documentation", "completed", 22),
        _run_status("user_flow", "completed", 25),
    ]
    search = FakeSearch()
    embed = Mock(return_value=[[0.1, 0.2]])
    retrieval = RetrievalUsecase(
        FakeSources(), FakeIndexing(statuses), search, FakeModels(), embed, None, 10
    )
    response = await retrieval.search_project_evidence(10, "how does upload retry work", 2)
    assert [kind for kind, _ in search.dense_calls] == ["user_flow", "documentation", "code"]
    assert [kind for kind, _ in search.lexical_calls] == ["user_flow", "documentation", "code"]
    assert [hit.index_type for hit in response.hits] == ["documentation", "code"]
    embed.assert_called_once()


async def test_answered_history_is_relevant_bounded_and_project_scoped(
    db_engine, git_source_id: int
) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.adapter.repositories.tickets import TicketSqlRepository

    async with db_engine.begin() as connection:
        other_project = await connection.scalar(
            text(
                "INSERT INTO sources (type, name, config) VALUES ('git', 'Other', '{}') RETURNING id"
            )
        )
        rows = await connection.execute(
            text("""
            INSERT INTO tickets (source_id, title, description, status, answer)
            VALUES
                (:source, 'UploadRetry current', 'RetryConnector', 'answered', 'Current'),
                (:other, 'UploadRetry another project', 'RetryConnector', 'answered', 'Secret'),
                (:source, 'UploadRetry unresolved', 'RetryConnector', 'escalated', 'Unresolved'),
                (:source, 'Separate symptom', 'Network share', 'answered', 'Irrelevant'),
                (:source, 'UploadRetry old case', 'RetryConnector', 'answered', 'Confirmed old'),
                (:source, 'UploadRetry recent case', 'RetryConnector', 'answered', 'Confirmed recent'),
                (:source, 'UploadRetry third case', 'RetryConnector', 'answered', 'Confirmed third'),
                (:source, 'UploadRetry fourth case', 'RetryConnector', 'answered', 'Confirmed fourth')
            RETURNING id
        """),
            {"source": git_source_id, "other": other_project},
        )
        ids = list(rows.scalars())
    async with AsyncSession(db_engine) as session:
        leads = await TicketSqlRepository(session).search_answered_history(
            git_source_id, ids[0], ["UploadRetry RetryConnector"]
        )
    assert len(leads) == 3
    assert {hit.ticket_id for hit in leads} <= set(ids[4:])
    assert all(hit.index_type == "ticket_history" and "lead only" in hit.content for hit in leads)
    assert all("Secret" not in hit.content for hit in leads)


async def test_resolver_uses_history_as_lead_without_citing_old_case() -> None:
    history = replace(_hit(0), index_type="ticket_history", ticket_id=18)
    code = _hit(2)
    response = json.dumps({**json.loads(ANSWER_JSON), "source_refs": ["S4", "S2"]})
    gateway = FakeGateway([response])
    usecase = _usecase(FakeTickets(), gateway)
    ticket = await usecase.create_ticket(1, "Upload unavailable", "HTTP 503 from connector")
    target = await usecase._target_for(1, fallback_error="missing model")
    assert target is not None

    result = await usecase._run_resolver(
        ticket, target, {"S4": history, "S2": code}, None, "strong", "test"
    )

    assert "[S4]" in gateway.prompts[0]
    assert result.source_refs == ["S2"]


def test_log_signatures_exclude_foreign_archives_and_private_metadata() -> None:
    own = replace(
        _hit(0),
        index_type="ticket-log",
        ticket_id=1,
        attachment_id=21,
        content=(
            'token="ENOSPC" deployment=OOMKilled service ECONNREFUSED version v2.ECONNRESET '
            "https://internal.example/ETIMEDOUT /private/ENOSPC ENOSPC.log"
        ),
    )
    other = replace(own, ticket_id=2, content="ERROR ENOSPC")
    unattached = replace(own, attachment_id=None, content="ERROR ENOSPC")
    project = replace(own, index_type="code", content="ERROR ENOSPC")
    assert scoped_log_error_signatures(1, [own, other, unattached, project]) == ()
    supported = replace(
        own,
        content='{"message":"write failed","errno":"ENOSPC","status":"HTTP 500","token":"ETIMEDOUT"}',
    )
    assert scoped_log_error_signatures(1, [own, supported]) == ("ENOSPC", "HTTP 500")


async def test_web_stage_passes_public_codes_only_from_current_attached_logs() -> None:
    tickets = FakeTickets()
    tools = FakeDiagnosticTools(
        DiagnosticEvidence("skipped", [], "omitted"),
        DiagnosticEvidence("empty", [], "no results"),
    )
    usecase = _usecase(tickets, FakeGateway([]), diagnostic_tools=tools)
    ticket = await usecase.create_ticket(1, "HTTP 500", "private context")
    own = replace(
        _hit(0),
        index_type="ticket-log",
        ticket_id=ticket.id,
        attachment_id=21,
        content="ENOENT involving https://internal.example/ECONNRESET; error=ENOSPC",
    )
    foreign = replace(own, ticket_id=ticket.id + 1, content="error=OOMKilled")

    external = replace(_hit(3), index_type="external_web", ticket_id=ticket.id)
    tools.search_web = AsyncMock(
        return_value=DiagnosticEvidence(
            "completed",
            [_hit(4), external, replace(external, ticket_id=foreign.ticket_id)],
            "results",
        )
    )
    result = await usecase._run_diagnostic_tool(
        {
            "ticket": ticket,
            "dossier": {"S1": own, "S2": foreign},
            "pending": ["web"],
            "run_id": None,
        },
        "web",
    )

    tools.search_web.assert_awaited_once_with(
        ticket.source_id, ticket.id, public_signatures=("ENOSPC",)
    )
    assert list(result["dossier"].values()) == [own, foreign, external]
