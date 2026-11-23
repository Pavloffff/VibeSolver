import json
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter import diagnostic_tools
from app.adapter.config import Settings
from app.adapter.diagnostic_tools import DiagnosticToolsAdapter
from app.domain.ui_observation import UiObservation

OBSERVATION = {
    "role": "button",
    "name": "Submit",
    "width": 120.0,
    "height": 34.0,
    "visible": True,
    "enabled": False,
    "checked": None,
    "observed_at": "2026-11-22T01:02:03Z",
}


@dataclass
class ScopedOptions:
    project_options: tuple[str | None, str | None, bool] = ("submit", "public", True)
    ticket_options: tuple[bool, str] | None = (False, "HTTP 503 /users/alice token=PrivateValue")
    ui_observation: UiObservation | None = None

    async def project(self, source_id: int) -> tuple[str | None, str | None, bool]:
        assert source_id == 10
        return self.project_options

    async def ticket(self, source_id: int, ticket_id: int) -> tuple[bool, str] | None:
        if (source_id, ticket_id) != (10, 20):
            return None
        return self.ticket_options

    async def observation(self, source_id: int, ticket_id: int) -> UiObservation | None:
        assert (source_id, ticket_id) == (10, 20)
        return self.ui_observation


@pytest.fixture
def options(monkeypatch: pytest.MonkeyPatch) -> ScopedOptions:
    options = ScopedOptions()
    monkeypatch.setattr(diagnostic_tools, "DiagnosticOptionsRepository", lambda session: options)
    return options


def adapter(handler: httpx.MockTransport) -> DiagnosticToolsAdapter:
    settings = Settings(
        diagnostic_ui_probes={"submit": "http://browser-observer"},
        diagnostic_web_providers={"public": "http://searxng"},
    )
    return DiagnosticToolsAdapter(AsyncSession(), settings, transport=handler)


def unexpected_request(request: httpx.Request) -> httpx.Response:
    pytest.fail(f"unexpected outbound request to {request.url.host}")


@pytest.mark.parametrize(
    ("project_options", "ticket_options"),
    [
        (("submit", None, True), (True, "HTTP 503")),
        (("submit", "unknown", True), (True, "HTTP 503")),
        (("submit", "public", False), (True, "HTTP 503")),
        (("submit", "public", True), (True, "Case 503 alice@private.example")),
        (("submit", "public", True), (True, "OOMKılled")),
        (("submit", "public", True), None),
    ],
)
async def test_web_search_requires_both_permissions_and_a_public_signature(
    options: ScopedOptions,
    project_options: tuple[str | None, str | None, bool],
    ticket_options: tuple[bool, str] | None,
) -> None:
    options.project_options = project_options
    options.ticket_options = ticket_options
    evidence = await adapter(httpx.MockTransport(unexpected_request)).search_web(10, 20)
    assert evidence.status == "skipped"
    assert evidence.hits == []


async def test_web_search_sends_only_public_signature_and_labels_bounded_results(
    options: ScopedOptions,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "searxng"
        assert request.url.path == "/search"
        assert dict(request.url.params) == {"q": "HTTP 503", "format": "json"}
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.com/unavailable?secret=value#private",
                        "title": "<b>Reference</b>",
                        "content": "<strong>HTTP 503</strong> " + "x" * 3000,
                    },
                    {"url": "javascript:alert(1)", "title": "Unsafe", "content": "Unsafe"},
                    {"url": "http://127.0.0.1/data", "title": "Local", "content": "Local"},
                    {"url": "http://127.1/data", "title": "Local", "content": "Local"},
                    {"url": "http://127.0.0.0x1/data", "title": "Local", "content": "Local"},
                ],
            },
        )

    evidence = await adapter(httpx.MockTransport(respond)).search_web(10, 20)
    assert evidence.status == "completed"
    assert "HTTP 503" in evidence.reason
    assert len(evidence.hits) == 1
    hit = evidence.hits[0]
    assert hit.index_type == "external_web"
    assert hit.branch == "searxng"
    assert hit.path == "https://example.com/unavailable"
    assert hit.ticket_id == 20
    assert hit.source_ref.startswith("ticket:20:external_web:")
    assert hit.path in hit.source_ref
    assert "Reference" in hit.content
    assert "<strong>" not in hit.content
    assert len(hit.content) < 1800


@pytest.mark.parametrize("response_kind", ["redirect", "oversized", "malformed"])
async def test_web_provider_failure_is_reported_without_forwarding_or_disclosing_details(
    options: ScopedOptions, response_kind: str
) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if response_kind == "redirect":
            return httpx.Response(302, headers={"location": "https://external.example/private"})
        if response_kind == "oversized":
            return httpx.Response(200, content=b"x" * 512_000)
        return httpx.Response(200, content=b"raw-searxng-error")

    evidence = await adapter(httpx.MockTransport(respond)).search_web(10, 20)
    assert evidence.status == "unavailable"
    assert evidence.hits == []
    assert "private" not in evidence.reason
    assert "raw-searxng-error" not in evidence.reason
    assert calls == ["searxng"]


async def test_ui_uses_scoped_engineer_observation_before_stand(options: ScopedOptions) -> None:
    options.ui_observation = UiObservation(
        role="button",
        name="Submit",
        width=120.0,
        height=34.0,
        visible=True,
        enabled=False,
        checked=None,
        observed_at=datetime(2026, 11, 22, 1, 2, 3, tzinfo=UTC),
    )
    tools = adapter(httpx.MockTransport(unexpected_request))

    unrelated = await tools.observe_ui(10, 99)
    assert unrelated.hits == []
    assert unrelated.status == "skipped"

    evidence = await tools.observe_ui(10, 20)
    assert evidence.status == "completed"
    assert "engineer" in evidence.reason.lower()
    assert len(evidence.hits) == 1
    assert evidence.hits[0].index_type == "ui_observation"
    assert evidence.hits[0].branch == "engineer"
    hit = evidence.hits[0]
    assert hit.ticket_id == 20
    assert hit.source_ref.startswith("ticket:20:ui_observation:engineer:")
    assert hit.event_timestamp == "2026-11-22T01:02:03+00:00"
    assert hit.event_timestamp in hit.source_ref
    content = json.loads(hit.content)
    assert content["name"] == "Submit"
    assert content["observed_at"] == hit.event_timestamp
    assert content["origin"] == "engineer"


async def test_ui_requests_only_configured_probe_and_labels_stand_observation(
    options: ScopedOptions,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "browser-observer"
        assert request.url.path == "/observe"
        assert dict(request.url.params) == {"probe": "submit"}
        return httpx.Response(200, json=OBSERVATION)

    evidence = await adapter(httpx.MockTransport(respond)).observe_ui(10, 20)
    assert evidence.status == "completed"
    assert len(evidence.hits) == 1
    hit = evidence.hits[0]
    assert hit.branch == "test_stand"
    assert hit.index_type == "ui_observation"
    assert hit.source_ref.startswith("ticket:20:ui_observation:test_stand:")
    assert json.loads(hit.content)["origin"] == "test_stand"
    assert "Submit" in hit.content
    assert "120" in hit.content


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"html": "<input password='secret'>"},
        {"height": "34"},
        {"observed_at": "2026-11-22T01:02:03"},
    ],
)
async def test_ui_rejects_invalid_stand_observations(
    options: ScopedOptions, invalid_fields: dict[str, object]
) -> None:
    evidence = await adapter(
        httpx.MockTransport(lambda request: httpx.Response(200, json=OBSERVATION | invalid_fields))
    ).observe_ui(10, 20)
    assert evidence.status == "unavailable"
    assert evidence.hits == []
    assert "secret" not in evidence.reason


async def test_scoped_log_error_can_replace_generic_title_signature(options: ScopedOptions) -> None:
    options.ticket_options = (False, "HTTP 500 for private service")

    def respond(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"q": "ENOSPC", "format": "json"}
        return httpx.Response(200, json={"results": []})

    evidence = await adapter(httpx.MockTransport(respond)).search_web(
        10, 20, public_signatures=("HTTP 500", "ENOSPC", "private service details")
    )
    assert evidence.status == "empty"


@pytest.mark.parametrize("project_allowed", [True, False])
async def test_web_never_sends_unvalidated_log_candidates(
    options: ScopedOptions, project_allowed: bool
) -> None:
    options.project_options = ("submit", "public", project_allowed)
    options.ticket_options = (False, "Trouble on deployment")
    evidence = await adapter(httpx.MockTransport(unexpected_request)).search_web(
        10, 20, public_signatures=("ENOSPC at https://private.local/secret?token=private",)
    )
    assert evidence.status == "skipped"


async def test_project_denial_blocks_valid_observed_error(options: ScopedOptions) -> None:
    options.project_options = ("submit", "public", False)
    evidence = await adapter(httpx.MockTransport(unexpected_request)).search_web(
        10, 20, public_signatures=("ENOSPC",)
    )
    assert evidence.status == "skipped"
