from dataclasses import replace

from app.domain.repositories.retrieval import SearchHit
from app.usecase.ticket_specialists import observed_runtime_facts


def test_runtime_comparison_keeps_versions_and_their_ticket_log_references() -> None:
    hit = SearchHit(
        "ticket-log",
        1,
        "incident.log",
        "",
        1,
        1,
        None,
        'platform=kubernetes service.version="2.1.0" api_key=secret',
        1,
        ticket_id=7,
    )
    dossier = {
        "S1": hit,
        "S2": replace(hit, content='{"service_version":"2.2.0","k8s.cluster.version":"v1.29.1"}'),
        "S3": replace(hit, ticket_id=9, content="environment=private"),
        "S4": replace(hit, index_type="documentation", content="environment=production"),
    }
    assert [
        (fact.field, fact.value, fact.source_ref) for fact in observed_runtime_facts(dossier, 7)
    ] == [
        ("platform", "kubernetes", "S1"),
        ("service_version", "2.1.0", "S1"),
        ("service_version", "2.2.0", "S2"),
        ("cluster_version", "v1.29.1", "S2"),
    ]


def test_runtime_facts_do_not_guess_a_platform_from_an_error_or_extract_urls() -> None:
    hit = SearchHit(
        "ticket-log",
        1,
        "app.log",
        "",
        1,
        1,
        None,
        "maybe kubernetes? version=2 platform=https://internal.example api_key=foo",
        1,
        ticket_id=8,
    )
    assert observed_runtime_facts({"S1": hit}, 8) == []
