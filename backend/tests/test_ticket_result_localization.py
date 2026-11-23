import json
from unittest.mock import Mock

import pytest

from app.domain.model_provider_entities import ProviderCredentials
from app.domain.repositories.material_generation import GeneratedJson
from app.usecase.ticket_result_localization import (
    TicketResultLocalizationError,
    localize_ticket_result,
)


async def test_localization_preserves_original_and_references() -> None:
    source = "См. [руководство](https://example.test/setup) и `config.toml` (S1)."
    completion = GeneratedJson(
        text="```json\n"
        + json.dumps(
            {
                "original_language": "ru",
                "en": "See [the guide](__REFERENCE_1__) and __REFERENCE_2__ (__REFERENCE_3__).",
                "ru": None,
                "zh": "请参阅[指南](__REFERENCE_1__)和 __REFERENCE_2__ (__REFERENCE_3__)。",
            }
        )
        + "\n```",
        input_tokens=100,
        output_tokens=70,
    )
    gateway = Mock()
    gateway.generate_json_with_usage.return_value = completion
    credentials = ProviderCredentials(3, "ollama", "local", "http://localhost", None)

    result, usage = await localize_ticket_result(
        source, None, gateway, credentials, "model", 30, 500
    )

    assert result.ru == source
    assert result.en == "See [the guide](https://example.test/setup) and `config.toml` (S1)."
    assert result.zh == "请参阅[指南](https://example.test/setup)和 `config.toml` (S1)。"
    assert usage == completion
    args = gateway.generate_json_with_usage.call_args.args
    assert args[:2] == (credentials, "model")
    assert json.loads(args[3]) == {
        "text": "См. [руководство](__REFERENCE_1__) и __REFERENCE_2__ (__REFERENCE_3__).",
        "original_language": None,
    }


@pytest.mark.parametrize(
    "translation", ["См. https://example.test/fake", "[См.](../fake)", '<a href="/fake">См.</a>']
)
async def test_localization_rejects_invented_link(translation: str) -> None:
    gateway = Mock()
    gateway.generate_json_with_usage.return_value = GeneratedJson(
        text=json.dumps(
            {
                "original_language": "en",
                "en": "Original answer",
                "ru": translation,
                "zh": "原始答案",
            }
        )
    )
    credentials = ProviderCredentials(3, "ollama", "local", "http://localhost", None)

    with pytest.raises(TicketResultLocalizationError) as rejected:
        await localize_ticket_result(
            "Original answer", "en", gateway, credentials, "model", 30, 500
        )
    assert rejected.value.usage == gateway.generate_json_with_usage.return_value


async def test_protects_english_even_when_another_locale_is_invalid() -> None:
    gateway = Mock()
    gateway.generate_json_with_usage.return_value = GeneratedJson(
        text=json.dumps(
            {"original_language": "ru", "en": "Check __REFERENCE_1__.", "ru": None, "zh": None}
        )
    )
    credentials = ProviderCredentials(3, "ollama", "local", "http://localhost", None)
    with pytest.raises(TicketResultLocalizationError) as error:
        await localize_ticket_result(
            "Проверьте `config.toml`.", None, gateway, credentials, "model", 30, 500
        )
    assert error.value.english_result == "Check `config.toml`."
