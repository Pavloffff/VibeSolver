import pytest

from app.adapter.config import Settings
from app.adapter.model_providers import providers
from app.adapter.model_providers.providers import (
    AnthropicAdapter,
    KimiAdapter,
    OpenAIAdapter,
    _anthropic_chat_completion,
    _openai_chat_completion,
    build_provider_registry,
)
from app.domain.model_provider_entities import (
    ProviderCredentials,
    ProviderUnavailableError,
)
from app.usecase.model_providers import (
    ModelProviderValidationError,
    normalize_provider_url,
)

KIMI_URL = "https://api.moonshot.ai/v1"
ANTHROPIC_URL = "https://api.anthropic.com"
OPENAI_URL = "https://api.openai.com/v1"


def _registry() -> dict:
    return build_provider_registry(
        Settings(
            kimi_api_url=KIMI_URL,
            anthropic_api_url=ANTHROPIC_URL,
            openai_api_url=OPENAI_URL,
        )
    )


def _credentials(provider_type: str, base_url: str) -> ProviderCredentials:
    return ProviderCredentials(
        id=1,
        provider_type=provider_type,
        name=provider_type,
        base_url=base_url,
        api_key="test-key",
    )


def test_cloud_providers_registered_after_default_zai() -> None:
    registry = _registry()
    assert list(registry)[:4] == ["zai", "kimi", "anthropic", "openai"]
    for provider_type, url in [
        ("kimi", KIMI_URL),
        ("anthropic", ANTHROPIC_URL),
        ("openai", OPENAI_URL),
    ]:
        definition = registry[provider_type]
        assert definition.default_url == url
        assert definition.requires_api_key is True
        assert definition.fixed_url is True
        assert definition.sync_all_models is False


def test_cloud_provider_urls_are_fixed() -> None:
    registry = _registry()
    for provider_type, url in [
        ("kimi", KIMI_URL),
        ("anthropic", ANTHROPIC_URL),
        ("openai", OPENAI_URL),
    ]:
        definition = registry[provider_type]
        assert normalize_provider_url(provider_type, f"{url}/", definition) == url
        with pytest.raises(ModelProviderValidationError):
            normalize_provider_url(provider_type, "https://evil.example/v1", definition)


def test_kimi_lists_kimi_and_moonshot_chat_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request_json(
        url: str, timeout: int, api_key: str | None = None, payload: dict | None = None
    ) -> dict:
        assert url == f"{KIMI_URL}/models"
        assert api_key == "test-key"
        return {
            "data": [
                {"id": "kimi-k2.6", "name": "Kimi K2.6"},
                {"id": "moonshot-v1-128k"},
                {"id": "deepseek-chat"},
            ]
        }

    monkeypatch.setattr(providers, "_request_json", fake_request_json)
    models = KimiAdapter().list_models(_credentials("kimi", KIMI_URL), timeout=5)
    assert [model.provider_model_id for model in models] == [
        "kimi-k2.6",
        "moonshot-v1-128k",
    ]
    assert all(model.capabilities == ["chat"] for model in models)


def test_anthropic_lists_claude_chat_models(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_request_json(
        url: str,
        timeout: int,
        api_key: str | None = None,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        seen["url"] = url
        seen["headers"] = headers
        return {
            "data": [
                {"id": "claude-opus-4-8", "display_name": "Claude Opus 4.8"},
                {"id": "claude-sonnet-5"},
            ]
        }

    monkeypatch.setattr(providers, "_request_json", fake_request_json)
    models = AnthropicAdapter().list_models(
        _credentials("anthropic", ANTHROPIC_URL), timeout=5
    )
    assert seen["url"] == f"{ANTHROPIC_URL}/v1/models"
    assert seen["headers"] == {"x-api-key": "test-key", "anthropic-version": "2023-06-01"}
    assert [model.provider_model_id for model in models] == [
        "claude-opus-4-8",
        "claude-sonnet-5",
    ]
    assert models[0].display_name == "Claude Opus 4.8"
    assert all(model.capabilities == ["chat"] for model in models)


def test_cloud_providers_support_json_generation() -> None:
    assert "kimi" in providers.CHAT_COMPLETION_ADAPTERS
    assert "anthropic" in providers.CHAT_COMPLETION_ADAPTERS
    assert "openai" in providers.CHAT_COMPLETION_ADAPTERS


def test_anthropic_chat_completion_posts_native_messages_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_request_json(
        url: str,
        timeout: int,
        api_key: str | None = None,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        seen["url"] = url
        seen["payload"] = payload
        seen["headers"] = headers
        return {"content": [{"type": "text", "text": "  {\"files\": []}  "}]}

    monkeypatch.setattr(providers, "_request_json", fake_request_json)
    result = _anthropic_chat_completion(
        ANTHROPIC_URL,
        "claude-opus-4-8",
        [
            {"role": "system", "content": "reply with json"},
            {"role": "user", "content": "generate docs"},
        ],
        timeout=30,
        api_key="test-key",
        max_output_tokens=8192,
    )
    assert result == '{"files": []}'
    assert seen["url"] == f"{ANTHROPIC_URL}/v1/messages"
    assert seen["headers"] == {"x-api-key": "test-key", "anthropic-version": "2023-06-01"}
    assert seen["payload"] == {
        "model": "claude-opus-4-8",
        "max_tokens": 8192,
        "system": "reply with json",
        "messages": [{"role": "user", "content": "generate docs"}],
    }


def test_anthropic_chat_completion_rejects_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        providers,
        "_request_json",
        lambda *args, **kwargs: {"content": [{"type": "text", "text": "   "}]},
    )
    with pytest.raises(ProviderUnavailableError):
        _anthropic_chat_completion(
            ANTHROPIC_URL,
            "claude-sonnet-5",
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ],
            timeout=5,
            api_key="test-key",
            max_output_tokens=100,
        )


def test_openai_lists_chat_models_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request_json(
        url: str,
        timeout: int,
        api_key: str | None = None,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        assert url == f"{OPENAI_URL}/models"
        assert api_key == "test-key"
        return {
            "data": [
                {"id": "gpt-5.2", "name": "GPT-5.2"},
                {"id": "chatgpt-4o-latest"},
                {"id": "o4-mini"},
                {"id": "text-embedding-3-large"},
                {"id": "dall-e-3"},
                {"id": "whisper-1"},
            ]
        }

    monkeypatch.setattr(providers, "_request_json", fake_request_json)
    models = OpenAIAdapter().list_models(
        _credentials("openai", OPENAI_URL), timeout=5
    )
    assert [model.provider_model_id for model in models] == [
        "gpt-5.2",
        "chatgpt-4o-latest",
        "o4-mini",
    ]
    assert all(model.capabilities == ["chat"] for model in models)


def test_openai_chat_completion_uses_new_parameter_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_request_json(
        url: str,
        timeout: int,
        api_key: str | None = None,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        calls.append({"url": url, "payload": dict(payload) if payload else payload})
        if len(calls) == 1:
            raise ProviderUnavailableError("Provider returned HTTP 400")
        return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}

    monkeypatch.setattr(providers, "_request_json", fake_request_json)
    result = _openai_chat_completion(
        OPENAI_URL,
        "gpt-5.2",
        [
            {"role": "system", "content": "reply with json"},
            {"role": "user", "content": "hi"},
        ],
        timeout=30,
        api_key="test-key",
        max_output_tokens=8192,
    )
    assert result == '{"ok": true}'
    first, second = calls
    assert first["url"] == f"{OPENAI_URL}/chat/completions"
    first_payload = first["payload"]
    assert "temperature" not in first_payload
    assert "max_tokens" not in first_payload
    assert first_payload["max_completion_tokens"] == 8192
    assert first_payload["response_format"] == {"type": "json_object"}
    assert "response_format" not in second["payload"]
