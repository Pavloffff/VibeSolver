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
        "Identify the documented user path and any assumptions or missing steps. Compare it "
        "with observed behavior; treat undocumented or conflicting behavior as a gap to verify "
        "against implementation.",
        short_route_evidence=True,
    ),
    "logs": SpecialistDefinition(
        frozenset({"ticket-log"}),
        "Connect symptoms to exact events in the attached logs. Cite observed service or deploy "
        "versions, platform, and settings explicitly applied at runtime only when a concrete "
        "line confirms them. Separate configured defaults, actual values, guesses, and absence "
        "of evidence. Distinguish correlation from cause.",
        ticket_scoped=True,
        run_with_evidence=True,
    ),
    "code": SpecialistDefinition(
        frozenset({"code"}),
        "Trace the relevant branch from the reported operation to the implementation. Verify "
        "documented behavior and settings against the actual code. Distinguish a mismatch, "
        "an unobserved deployed version, and a confirmed defect before concluding.",
    ),
}

_RESERVED_ROLES = frozenset(
    {
        "triage",
        "log_intake",
        "investigate",
        "read_code",
        "recheck",
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
