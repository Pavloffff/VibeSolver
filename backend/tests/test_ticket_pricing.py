from decimal import Decimal

import pytest

from app.usecase.ticket_pricing import parse_pricing, step_cost_usd


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        (
            {"pricing": {"prompt": "0.000001", "completion": "0.000002"}},
            (Decimal("0.000001"), Decimal("0.000002")),
        ),
        ({}, None),
        ({"pricing": {"prompt": "free", "completion": "0.2"}}, None),
        ({"pricing": {"prompt": "-0.1", "completion": "0.2"}}, None),
    ],
)
def test_parse_pricing(metadata: dict, expected: tuple[Decimal, Decimal] | None) -> None:
    assert parse_pricing(metadata) == expected


def test_step_cost_usd() -> None:
    assert step_cost_usd((Decimal("0.000001"), Decimal("0.000002")), 100, 50) == pytest.approx(
        0.0002
    )
    assert step_cost_usd(None, 100, 50) is None
    assert step_cost_usd((Decimal("0.1"), Decimal("0.2")), None, 50) is None
