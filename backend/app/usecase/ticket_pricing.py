from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


def parse_pricing(metadata: Mapping[str, Any]) -> tuple[Decimal, Decimal] | None:
    pricing = metadata.get("pricing")
    if not isinstance(pricing, Mapping):
        return None
    try:
        per_input = Decimal(str(pricing["prompt"]))
        per_output = Decimal(str(pricing["completion"]))
    except (KeyError, InvalidOperation, ValueError):
        return None
    if per_input < 0 or per_output < 0:
        return None
    return per_input, per_output


def step_cost_usd(
    pricing: tuple[Decimal, Decimal] | None,
    tokens_in: int | None,
    tokens_out: int | None,
) -> float | None:
    if pricing is None or tokens_in is None or tokens_out is None:
        return None
    per_input, per_output = pricing
    return float(Decimal(tokens_in) * per_input + Decimal(tokens_out) * per_output)
