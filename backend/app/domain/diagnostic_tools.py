import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from app.domain.repositories.retrieval import SearchHit

_PUBLIC_SIGNATURES = {
    signature.lower(): signature
    for signature in (
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
}
_SIGNATURE_ALTERNATIVES = "|".join(map(re.escape, _PUBLIC_SIGNATURES.values()))
_TITLE_SIGNATURE = re.compile(rf"\b(?ai:{_SIGNATURE_ALTERNATIVES})\b")
_LOG_SIGNATURE = re.compile(
    rf"(?<![\w./@:\\-])\b(?ai:{_SIGNATURE_ALTERNATIVES})\b(?![\w/@:\\-]|\.\w)"
)
_LOG_URL = re.compile(r"(?ai)\b(?:[a-z][a-z0-9+.-]*://|www\.)[^\s<>]+")
_LOG_FIELD = re.compile(
    r"""(?ai)(?<![\w])["']?(?P<key>[a-z][\w.-]*)["']?[ 	]*[:=][ 	]*"""
    r"""(?P<value>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|HTTP[ 	]+[45][0-9]{2}|[^\s,}\]]+)"""
)
_LOG_METADATA_VALUE = re.compile(
    r"""(?ai)\b(?:version|build|release|platform|deployment|service|token|password|secret|api[-_ ]?key)"""
    r"""[ \t]+(?:"[^"\r\n]*"|'[^'\r\n]*'|`[^`\r\n]*`|HTTP[ \t]+[45][0-9]{2}|[^\s,}\]]+)"""
)
_DIAGNOSTIC_FIELDS = frozenset(
    {
        "error",
        "errno",
        "error_code",
        "errorcode",
        "exception",
        "failed",
        "failure",
        "http_status",
        "reason",
        "response_code",
        "status",
        "status_code",
    }
)


def choose_public_signature(title: str, observed: tuple[str, ...] = ()) -> str | None:
    allowed = frozenset(_PUBLIC_SIGNATURES.values())
    candidates = [signature for signature in observed if signature in allowed]
    title_match = _TITLE_SIGNATURE.search(title)
    if title_match is not None:
        candidates.append(_PUBLIC_SIGNATURES[title_match.group().lower()])
    return min(
        candidates,
        key=lambda signature: 2 if signature == "HTTP 500" else int(signature.startswith("HTTP ")),
        default=None,
    )


def scoped_log_error_signatures(ticket_id: int, hits: Iterable[SearchHit]) -> tuple[str, ...]:
    eligible = [
        hit
        for hit in hits
        if hit.index_type == "ticket-log"
        and hit.ticket_id == ticket_id
        and hit.attachment_id is not None
    ]
    signatures: dict[str, None] = {}
    for hit in sorted(
        eligible,
        key=lambda item: item.rerank_score if item.rerank_score is not None else item.score,
        reverse=True,
    )[:12]:
        observed = _LOG_URL.sub(" ", hit.content[:4000])
        observed = _LOG_FIELD.sub(
            lambda field: (
                f"\n{field['value']}\n" if field["key"].lower() in _DIAGNOSTIC_FIELDS else " "
            ),
            observed,
        )
        observed = _LOG_METADATA_VALUE.sub(" ", observed)
        for match in _LOG_SIGNATURE.finditer(observed):
            signatures[_PUBLIC_SIGNATURES[match.group().lower()]] = None
    return tuple(signatures)


@dataclass(frozen=True, slots=True)
class DiagnosticEvidence:
    status: str
    hits: list[SearchHit]
    reason: str


class DiagnosticTools(Protocol):
    async def observe_ui(self, source_id: int, ticket_id: int) -> DiagnosticEvidence: ...

    async def search_web(
        self, source_id: int, ticket_id: int, *, public_signatures: tuple[str, ...] = ()
    ) -> DiagnosticEvidence: ...
