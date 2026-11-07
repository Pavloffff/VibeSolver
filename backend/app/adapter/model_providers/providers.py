import json
from collections.abc import Iterator, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.adapter.config import Settings, get_settings
from app.domain.model_provider_entities import (
    ModelProviderDefinition,
    ProviderCredentials,
    ProviderModel,
    ProviderUnavailableError,
)


def _request_json(
    url: str,
    timeout: int,
    api_key: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        messages = {
            401: "API key is invalid or missing",
            403: "Provider denied access",
            404: "Provider endpoint was not found",
            429: "Provider rate limit exceeded",
        }
        raise ProviderUnavailableError(
            messages.get(exc.code, f"Provider returned HTTP {exc.code}")
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailableError(
            "Could not connect to provider; check its address and availability"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderUnavailableError("Provider returned an invalid response") from exc
    if not isinstance(value, dict):
        raise ProviderUnavailableError("Provider returned an invalid response")
    return value


def _model_rows(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = response.get("data", response.get("models", []))
    return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


class FreeTokenAdapter:
    def list_models(self, connection: ProviderCredentials, timeout: int) -> list[ProviderModel]:
        response = _request_json(
            f"{connection.base_url.rstrip('/')}/models", timeout, connection.api_key
        )
        models: list[ProviderModel] = []
        for row in _model_rows(response):
            model_id = row.get("id") or row.get("name")
            if not isinstance(model_id, str) or not model_id:
                continue
            models.append(
                ProviderModel(
                    provider_model_id=model_id,
                    display_name=str(row.get("name") or model_id),
                    capabilities=["chat"],
                    status="available",
                    metadata={"source": "served"},
                )
            )
        return models

    def pull_model(
        self, connection: ProviderCredentials, model_id: str, timeout: int
    ) -> Iterator[dict[str, Any]]:
        raise ProviderUnavailableError("FreeToken models are loaded by the FreeToken server")


class OllamaAdapter:
    def list_models(self, connection: ProviderCredentials, timeout: int) -> list[ProviderModel]:
        response = _request_json(f"{connection.base_url.rstrip('/')}/api/tags", timeout)
        models: list[ProviderModel] = []
        for row in _model_rows(response):
            model_id = row.get("name") or row.get("model")
            if not isinstance(model_id, str) or not model_id:
                continue
            try:
                details = _request_json(
                    f"{connection.base_url.rstrip('/')}/api/show",
                    timeout,
                    payload={"model": model_id},
                )
            except ProviderUnavailableError:
                details = {}
            capabilities = _ollama_capabilities(details)
            models.append(
                ProviderModel(
                    provider_model_id=model_id,
                    display_name=model_id,
                    capabilities=capabilities,
                    status="installed",
                    metadata={
                        "size_bytes": _optional_int(row.get("size")),
                        "family": _nested_string(row, "details", "family"),
                        "parameter_size": _nested_string(row, "details", "parameter_size"),
                        "quantization": _nested_string(row, "details", "quantization_level"),
                    },
                )
            )
        return models

    def pull_model(
        self, connection: ProviderCredentials, model_id: str, timeout: int
    ) -> Iterator[dict[str, Any]]:
        request = Request(
            f"{connection.base_url.rstrip('/')}/api/pull",
            data=json.dumps({"name": model_id, "stream": True}).encode("utf-8"),
            headers={"Accept": "application/x-ndjson", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                for line in response:
                    if line.strip():
                        value = json.loads(line.decode("utf-8"))
                        if isinstance(value, dict):
                            yield value
        except HTTPError as exc:
            raise ProviderUnavailableError(
                f"Ollama returned HTTP {exc.code} while loading the model"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailableError(
                "Ollama connection was interrupted during model loading"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderUnavailableError("Ollama returned an invalid pull response") from exc


class OpenRouterAdapter:
    def list_models(self, connection: ProviderCredentials, timeout: int) -> list[ProviderModel]:
        if not connection.api_key:
            raise ProviderUnavailableError("OpenRouter API key is required")
        base_url = connection.base_url.rstrip("/")
        chat_rows = _model_rows(_request_json(f"{base_url}/models", timeout, connection.api_key))
        embedding_rows = _model_rows(
            _request_json(f"{base_url}/embeddings/models", timeout, connection.api_key)
        )
        models: dict[str, ProviderModel] = {}
        for row, capability in [
            *((item, "chat") for item in chat_rows),
            *((item, "embedding") for item in embedding_rows),
        ]:
            model_id = row.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue
            model = models.get(model_id)
            if model is None:
                model = ProviderModel(
                    provider_model_id=model_id,
                    display_name=str(row.get("name") or model_id),
                    status="available",
                    metadata={},
                )
                models[model_id] = model
            if capability not in model.capabilities:
                model.capabilities.append(capability)
            context = row.get("context_length")
            if isinstance(context, int):
                model.metadata["context_length"] = context
            pricing = row.get("pricing")
            if isinstance(pricing, dict):
                model.metadata["pricing"] = pricing
        return list(models.values())

    def pull_model(
        self, connection: ProviderCredentials, model_id: str, timeout: int
    ) -> Iterator[dict[str, Any]]:
        raise ProviderUnavailableError(
            "OpenRouter models are hosted remotely and cannot be downloaded"
        )


def build_provider_registry(settings: Settings | None = None) -> dict[str, ModelProviderDefinition]:
    config = settings or get_settings()
    return {
        "freetoken": ModelProviderDefinition(
            adapter=FreeTokenAdapter(),
            default_url=config.freetoken_api_url,
            display_name="FreeToken",
            requires_api_key=False,
        ),
        "ollama": ModelProviderDefinition(
            adapter=OllamaAdapter(),
            default_url=config.ollama_api_url,
            display_name="Ollama",
            requires_api_key=False,
            supports_model_pull=True,
        ),
        "openrouter": ModelProviderDefinition(
            adapter=OpenRouterAdapter(),
            default_url=config.openrouter_api_url,
            display_name="OpenRouter",
            requires_api_key=True,
            fixed_url=True,
            sync_all_models=False,
        ),
    }


def _ollama_capabilities(response: dict[str, Any]) -> list[str]:
    raw = response.get("capabilities", [])
    values = (
        {item.lower() for item in raw if isinstance(item, str)} if isinstance(raw, list) else set()
    )
    capabilities: list[str] = []
    if values.intersection({"completion", "tools", "vision"}):
        capabilities.append("chat")
    if "embedding" in values:
        capabilities.append("embedding")
    return capabilities


def _nested_string(value: dict[str, Any], outer: str, inner: str) -> str | None:
    nested = value.get(outer)
    result = nested.get(inner) if isinstance(nested, dict) else None
    return result if isinstance(result, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None
