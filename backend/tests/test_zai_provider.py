import pytest

from app.adapter.config import Settings
from app.adapter.model_providers import providers
from app.adapter.model_providers.providers import (
    ZaiAdapter,
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

ZAI_URL = "https://api.z.ai/api/paas/v4"


def _registry() -> dict:
    return build_provider_registry(Settings(zai_api_url=ZAI_URL))


def _credentials(api_key: str | None = "test-key") -> ProviderCredentials:
    return ProviderCredentials(
        id=1,
        provider_type="zai",
        name="Z.ai",
        base_url=ZAI_URL,
        api_key=api_key,
    )


def test_zai_is_the_default_catalog_provider() -> None:
    registry = _registry()
    assert next(iter(registry)) == "zai"
    definition = registry["zai"]
    assert definition.display_name == "Z.ai"
    assert definition.default_url == ZAI_URL
    assert definition.requires_api_key is True
    assert definition.fixed_url is True
    assert definition.sync_all_models is False


def test_zai_url_is_fixed() -> None:
    definition = _registry()["zai"]
    assert normalize_provider_url("zai", f"{ZAI_URL}/", definition) == ZAI_URL
    with pytest.raises(ModelProviderValidationError):
        normalize_provider_url("zai", "https://evil.example/api/paas/v4", definition)


def test_zai_lists_glm_chat_models_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request_json(url: str, timeout: int, api_key: str | None = None) -> dict:
        assert url == f"{ZAI_URL}/models"
        assert api_key == "test-key"
        return {
            "data": [
                {"id": "glm-4.6", "name": "GLM-4.6"},
                {"id": "glm-4.5-air"},
                {"id": "embedding-3"},
                {"id": "cogview-4"},
                {"owned_by": "zai"},
            ]
        }

    monkeypatch.setattr(providers, "_request_json", fake_request_json)
    models = ZaiAdapter().list_models(_credentials(), timeout=5)
    assert [model.provider_model_id for model in models] == ["glm-4.6", "glm-4.5-air"]
    assert all(model.capabilities == ["chat"] for model in models)
    assert all(model.status == "available" for model in models)


def test_zai_requires_api_key_to_list_models() -> None:
    with pytest.raises(ProviderUnavailableError):
        ZaiAdapter().list_models(_credentials(api_key=None), timeout=5)


def test_zai_supports_json_generation() -> None:
    assert "zai" in providers.CHAT_COMPLETION_ADAPTERS
