import asyncio
import ipaddress
import json
import re
from datetime import UTC, datetime
from html import unescape

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter.config import Settings
from app.adapter.repositories.diagnostic_options import DiagnosticOptionsRepository
from app.domain.diagnostic_tools import DiagnosticEvidence
from app.domain.repositories.retrieval import SearchHit
from app.domain.ui_observation import UiObservation

MAX_PROBE_BYTES = 4096
MAX_SEARCH_BYTES = 256 * 1024
MAX_WEB_RESULTS = 3
MAX_WEB_URL = 1024
MAX_WEB_TITLE = 200
MAX_WEB_SNIPPET = 1200
PUBLIC_ERROR_SIGNATURES = (
    "HTTP 400",
    "HTTP 401",
    "HTTP 403",
    "HTTP 404",
    "HTTP 408",
    "HTTP 429",
    "HTTP 500",
    "HTTP 502",
    "HTTP 503",
    "HTTP 504",
    "ECONNREFUSED",
    "ECONNRESET",
    "ENOSPC",
    "ETIMEDOUT",
    "OOMKilled",
)
PUBLIC_ERROR_PATTERN = re.compile(
    r"\b(?ai:" + "|".join(map(re.escape, PUBLIC_ERROR_SIGNATURES)) + r")\b"
)
TAG_PATTERN = re.compile(r"<[^<>]*>")
DOMAIN_PATTERN = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


class DiagnosticResponseError(ValueError):
    pass


class DiagnosticToolsAdapter:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._options = DiagnosticOptionsRepository(session)
        self._settings = settings
        self._transport = transport

    async def observe_ui(self, source_id: int, ticket_id: int) -> DiagnosticEvidence:
        if await self._options.ticket(source_id, ticket_id) is None:
            return DiagnosticEvidence("skipped", [], "The ticket is outside the project scope.")
        try:
            observation = await self._options.observation(source_id, ticket_id)
        except ValidationError:
            return DiagnosticEvidence("unavailable", [], "The engineer observation was invalid.")
        if observation is not None:
            return DiagnosticEvidence(
                "completed",
                [_ui_hit(ticket_id, observation, "engineer", "Engineer-supplied UI observation")],
                "Used the engineer-supplied UI observation.",
            )

        probe, _, _ = await self._options.project(source_id)
        base_url = self._settings.diagnostic_ui_probes.get(probe) if probe else None
        if not base_url or probe is None:
            return DiagnosticEvidence("skipped", [], "The project has no configured UI probe.")
        try:
            response = await self._request(base_url, "observe", {"probe": probe}, MAX_PROBE_BYTES)
            observation = UiObservation.model_validate_json(response)
        except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError):
            return DiagnosticEvidence("unavailable", [], "The test stand UI observation failed.")
        return DiagnosticEvidence(
            "completed",
            [_ui_hit(ticket_id, observation, "test_stand", "Test stand UI observation")],
            "Observed the configured test stand.",
        )

    async def search_web(self, source_id: int, ticket_id: int) -> DiagnosticEvidence:
        ticket = await self._options.ticket(source_id, ticket_id)
        if ticket is None:
            return DiagnosticEvidence("skipped", [], "The ticket is outside the project scope.")
        _, title = ticket
        _, provider, enabled = await self._options.project(source_id)
        if not enabled:
            return DiagnosticEvidence("skipped", [], "Web search is disabled for this project.")
        base_url = self._settings.diagnostic_web_providers.get(provider) if provider else None
        if not base_url:
            return DiagnosticEvidence("skipped", [], "The project has no configured web provider.")

        signature = _public_signature(title)
        if signature is None:
            return DiagnosticEvidence(
                "skipped", [], "No approved public error signature was found."
            )
        try:
            response = await self._request(
                base_url, "search", {"q": signature, "format": "json"}, MAX_SEARCH_BYTES
            )
            hits = _web_hits(ticket_id, json.loads(response))
        except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError, RecursionError):
            return DiagnosticEvidence("unavailable", [], f"SearXNG search failed for {signature}.")
        if not hits:
            return DiagnosticEvidence(
                "empty", [], f"SearXNG found no usable results for {signature}."
            )
        return DiagnosticEvidence("completed", hits, f"SearXNG searched for {signature}.")

    async def _request(
        self, base_url: str, path: str, params: dict[str, str], max_bytes: int
    ) -> bytes:
        base = httpx.URL(base_url)
        if (
            base.scheme not in {"http", "https"}
            or not base.host
            or base.userinfo
            or base.query
            or base.fragment
        ):
            raise DiagnosticResponseError("Invalid diagnostic service URL")
        url = base.copy_with(path=f"{base.path.rstrip('/')}/{path}")
        timeout = self._settings.provider_request_timeout_seconds
        async with (
            asyncio.timeout(timeout),
            httpx.AsyncClient(
                transport=self._transport,
                timeout=timeout,
                trust_env=False,
                follow_redirects=False,
            ) as client,
            client.stream(
                "GET",
                url,
                params=params,
                headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            ) as response,
        ):
            response.raise_for_status()
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise DiagnosticResponseError("Unexpected diagnostic response encoding")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > max_bytes:
                    raise DiagnosticResponseError("Diagnostic response exceeds the size limit")
                body.extend(chunk)
            return bytes(body)


def _ui_hit(ticket_id: int, observation: UiObservation, origin: str, label: str) -> SearchHit:
    observed_at = observation.observed_at.isoformat()
    content = observation.model_dump(exclude={"observed_at"})
    content.update(origin=origin, observed_at=observed_at)
    return SearchHit(
        index_type="ui_observation",
        run_id=0,
        path=label,
        branch=origin,
        start_line=None,
        end_line=None,
        symbol=None,
        content=json.dumps(content, ensure_ascii=False),
        score=1.0,
        ticket_id=ticket_id,
        event_timestamp=observed_at,
    )


def _public_signature(text: str) -> str | None:
    match = PUBLIC_ERROR_PATTERN.search(text)
    if match is None:
        return None
    return next(
        (
            signature
            for signature in PUBLIC_ERROR_SIGNATURES
            if signature.casefold() == match.group().casefold()
        ),
        None,
    )


def _web_hits(ticket_id: int, response: object) -> list[SearchHit]:
    if not isinstance(response, dict) or not isinstance(results := response.get("results"), list):
        raise DiagnosticResponseError("Invalid search result schema")
    hits: list[SearchHit] = []
    seen_urls: set[str] = set()
    observed_at = datetime.now(UTC).isoformat()
    for result in results:
        if not isinstance(result, dict):
            continue
        url = _public_url(result.get("url"))
        title = _plain_text(result.get("title"), MAX_WEB_TITLE)
        snippet = _plain_text(result.get("content"), MAX_WEB_SNIPPET)
        if url is None or url in seen_urls or not (title or snippet):
            continue
        hits.append(
            SearchHit(
                index_type="external_web",
                run_id=0,
                path=url,
                branch="searxng",
                start_line=None,
                end_line=None,
                symbol=None,
                content=json.dumps({"title": title, "snippet": snippet}, ensure_ascii=False),
                score=1.0,
                ticket_id=ticket_id,
                event_timestamp=observed_at,
            )
        )
        seen_urls.add(url)
        if len(hits) == MAX_WEB_RESULTS:
            break
    return hits


def _public_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > MAX_WEB_URL or "\\" in value:
        return None
    if any(char.isspace() or not char.isprintable() for char in value):
        return None
    try:
        url = httpx.URL(value)
    except (httpx.InvalidURL, ValueError):
        return None
    host = url.raw_host.decode("ascii").rstrip(".").lower()
    if url.scheme not in {"https", "http"} or url.userinfo or "%" in host:
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not DOMAIN_PATTERN.fullmatch(host) or host.endswith(
            (".localhost", ".local", ".internal")
        ):
            return None
    else:
        if not address.is_global or address.is_multicast:
            return None
    return str(url.copy_with(query=None, fragment=None))


def _plain_text(value: object, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    text = TAG_PATTERN.sub(" ", unescape(value[: max_length * 4]))
    return " ".join("".join(char if char.isprintable() else " " for char in text).split())[
        :max_length
    ]
