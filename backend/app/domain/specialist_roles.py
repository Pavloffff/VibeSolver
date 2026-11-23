import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpecialistDefinition:
    index_types: frozenset[str]
    prompt: str
    ticket_scoped: bool = False
    run_with_evidence: bool = False
    short_route_evidence: bool = False


SPECIALIST_REGISTRY: dict[str, SpecialistDefinition] = {
    "flow": SpecialistDefinition(
        frozenset({"user_flow", "documentation"}),
        "Verify expected behavior against documented user flows.",
        short_route_evidence=True,
    ),
    "logs": SpecialistDefinition(
        frozenset({"ticket-log"}),
        "Connect symptoms to events in the attached logs and distinguish correlation from cause.",
        ticket_scoped=True,
        run_with_evidence=True,
    ),
    "code": SpecialistDefinition(
        frozenset({"code"}), "Check the reported behavior against the implementation."
    ),
}

_RESERVED_ROLES = frozenset(
    {
        "triage",
        "investigate",
        "ui",
        "web",
        "resolve",
        "resolve_models",
        "review",
        "answer",
        "escalate",
    }
)


def register_specialist(role: str, definition: SpecialistDefinition) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", role):
        raise ValueError("Invalid specialist role")
    if role in SPECIALIST_REGISTRY or role in _RESERVED_ROLES or role.startswith("escalate_"):
        raise ValueError("Specialist role already exists or is reserved")
    if not definition.index_types or not definition.prompt.strip():
        raise ValueError("A specialist must define its evidence types and prompt")
    SPECIALIST_REGISTRY[role] = definition
