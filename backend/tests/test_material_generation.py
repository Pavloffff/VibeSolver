import json
from unittest.mock import Mock

import pytest

from app.domain.repositories.material_generation import RetrievedChunk
from app.usecase.material_generation import (
    MATERIAL_GENERATOR_REGISTRY,
    MaterialGenerationConfig,
    MaterialGenerationUsecase,
    _normalize_user_flow_content,
)


@pytest.mark.parametrize("category", ["documentation", "user_flow"])
def test_generation_requests_english_prose_with_original_identifiers(category: str) -> None:
    prompt = MATERIAL_GENERATOR_REGISTRY[category].system_prompt

    assert "English" in prompt
    assert "identifiers" in prompt


def test_generated_markdown_uses_english_citations_and_preserves_source_paths() -> None:
    usecase = MaterialGenerationUsecase(Mock(), Mock(), Mock(), Mock(), Mock(), Mock(), Mock())
    source = RetrievedChunk(
        1, "code", "src/reports.py", "main", 12, 18, "get_reports", "original code", {}, 1
    )

    result = usecase._normalize_generated_content(
        "documentation", "reports.md", "# Reports\n", [source], ["S1"], {}, 1
    )

    assert result == "# Reports\n\n## Sources\n- `src/reports.py` · lines 12–18\n"


def test_generated_flow_fallbacks_are_english() -> None:
    flows = json.loads(
        _normalize_user_flow_content(
            '[{"steps":[{"action":"Call GET /reports","expected_result":"Reports are listed"}]}]'
        )
    )

    assert flows[0]["title"] == "User workflow"
    assert flows[0]["actor"] == "User"
    assert flows[0]["steps"][0]["action"] == "Call GET /reports"


@pytest.mark.asyncio
async def test_documentation_synthesis_and_repair_request_english() -> None:
    gateway = Mock()
    synopsis = (
        "The reports handler lists reports available to the caller and preserves repository order."
    )
    gateway.generate_json.side_effect = ["invalid JSON", json.dumps({"summary": synopsis})]
    config = MaterialGenerationConfig(10, 1024, 10, 2000, 3, 1200, 2400)
    usecase = MaterialGenerationUsecase(Mock(), Mock(), Mock(), Mock(), gateway, Mock(), config)

    summary = await usecase._synthesize_documentation("get_reports()", ["S1"], Mock(), "model")

    assert summary == synopsis + "\nEvidence IDs used: S1"
    assert all("English" in call.args[2] for call in gateway.generate_json.call_args_list)
