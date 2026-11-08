import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

USER_FLOW_PARSER_VERSION = "approved-json-flow-v1"
USER_FLOW_CHUNKER_VERSION = "flow-as-entity-v1"


class UserFlowStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)


class UserFlowDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    steps: list[UserFlowStep] = Field(min_length=1)
    components: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    doc_refs: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    approved: bool


def parse_user_flows(content: bytes) -> list[UserFlowDocument]:
    try:
        value = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("User Flow must be a UTF-8 JSON file") from exc
    raw_flows = value if isinstance(value, list) else [value]
    if not raw_flows:
        raise ValueError("User Flow file contains no scenarios")
    try:
        flows = [UserFlowDocument.model_validate(item) for item in raw_flows]
    except ValidationError as exc:
        raise ValueError("User Flow does not match the required structured format") from exc
    return flows


def parse_approved_flows(content: bytes) -> list[UserFlowDocument]:
    flows = parse_user_flows(content)
    if any(not flow.approved for flow in flows):
        raise ValueError("User Flow scenarios must be approved before indexing")
    return flows


def render_flow_for_search(flow: UserFlowDocument) -> str:
    lines = [f"Flow: {flow.title}", f"Actor: {flow.actor}", "Steps:"]
    lines.extend(
        f"{position}. {step.action} → expected: {step.expected_result}"
        for position, step in enumerate(flow.steps, start=1)
    )
    for label, values in (
        ("Components", flow.components),
        ("Failure modes", flow.failure_modes),
        ("Checklist", flow.checklist),
        ("Documentation references", flow.doc_refs),
    ):
        if values:
            lines.append(f"{label}: " + "; ".join(values))
    return "\n".join(lines)
