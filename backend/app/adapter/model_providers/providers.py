import json
from collections.abc import Callable, Iterator, Mapping
from math import isfinite
from typing import Any, TypedDict
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
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if api_key:
        request_headers["Authorization"] = f"Bearer {api_key}"
    if headers:
        request_headers.update(headers)
    request = Request(
        url, data=body, headers=request_headers, method="POST" if body is not None else "GET"
    )
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


def embed_texts(
    provider_type: str,
    base_url: str,
    model_id: str,
    texts: list[str],
    timeout: int,
    api_key: str | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    if provider_type == "ollama":
        response = _request_json(
            f"{base_url.rstrip('/')}/api/embed",
            timeout,
            payload={"model": model_id, "input": texts},
        )
        values = response.get("embeddings")
        if not isinstance(values, list):
            raise ProviderUnavailableError("Ollama returned an invalid embedding response")
        embeddings = [_validated_embedding(value) for value in values]
    elif provider_type == "freetoken":
        response = _request_json(
            f"{base_url.rstrip('/')}/embeddings",
            timeout,
            api_key,
            {"model": model_id, "input": texts},
        )
        rows = _model_rows(response)
        rows.sort(
            key=lambda row: row.get("index", 0) if isinstance(row.get("index", 0), int) else 0
        )
        embeddings = [_validated_embedding(row.get("embedding")) for row in rows]
    else:
        raise ProviderUnavailableError(
            "Indexing source code and project files requires an approved local embedding provider"
        )
    if len(embeddings) != len(texts):
        raise ProviderUnavailableError(
            "Provider returned a different number of embeddings than inputs"
        )
    dimensions = {len(embedding) for embedding in embeddings}
    if len(dimensions) != 1:
        raise ProviderUnavailableError("Provider returned embeddings with inconsistent dimensions")
    return embeddings


ChatCompletionAdapter = Callable[
    [str, str, list[dict[str, str]], int, str | None, int],
    "tuple[str, GenerationUsage]",
]
CHAT_COMPLETION_ADAPTERS: dict[str, ChatCompletionAdapter] = {}


class GenerationUsage(TypedDict):
    input_tokens: int | None
    output_tokens: int | None


def register_chat_completion_adapter(provider_type: str, adapter: ChatCompletionAdapter) -> None:
    normalized_type = provider_type.strip()
    if not normalized_type:
        raise ValueError("provider type must not be empty")
    CHAT_COMPLETION_ADAPTERS[normalized_type] = adapter


def complete_json(
    provider_type: str,
    base_url: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
    api_key: str | None = None,
    max_output_tokens: int = 8192,
) -> str:
    text, _usage = complete_json_with_usage(
        provider_type,
        base_url,
        model_id,
        system_prompt,
        user_prompt,
        timeout,
        api_key,
        max_output_tokens,
    )
    return text


def complete_json_with_usage(
    provider_type: str,
    base_url: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
    api_key: str | None = None,
    max_output_tokens: int = 8192,
) -> tuple[str, GenerationUsage]:
    adapter = CHAT_COMPLETION_ADAPTERS.get(provider_type)
    if adapter is None:
        raise ProviderUnavailableError("This model provider does not support text generation")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return adapter(base_url, model_id, messages, timeout, api_key, max_output_tokens)


def _ollama_chat_completion(
    base_url: str,
    model_id: str,
    messages: list[dict[str, str]],
    timeout: int,
    api_key: str | None,
    max_output_tokens: int,
) -> "tuple[str, GenerationUsage]":
    response = _request_json(
        f"{base_url.rstrip('/')}/api/chat",
        timeout,
        payload={
            "model": model_id,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": max_output_tokens},
        },
    )
    message = response.get("message")
    return _chat_content(message), _ollama_usage(response)


def _openai_compatible_chat_completion(
    base_url: str,
    model_id: str,
    messages: list[dict[str, str]],
    timeout: int,
    api_key: str | None,
    max_output_tokens: int,
) -> "tuple[str, GenerationUsage]":
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "response_format": {"type": "json_object"},
    }
    try:
        response = _request_json(
            f"{base_url.rstrip('/')}/chat/completions", timeout, api_key, payload
        )
    except ProviderUnavailableError as exc:
        if "HTTP 400" not in str(exc):
            raise
        payload.pop("response_format")
        response = _request_json(
            f"{base_url.rstrip('/')}/chat/completions", timeout, api_key, payload
        )
    return _chat_content(_first_message(response)), _openai_usage(response)


def _catalog_chat_models(
    response: Mapping[str, Any],
    prefix: str | None = None,
    prefixes: tuple[str, ...] | None = None,
    source: str = "catalog",
) -> list[ProviderModel]:
    accepted = prefixes if prefixes is not None else ((prefix,) if prefix else ())
    models: list[ProviderModel] = []
    for row in _model_rows(response):
        model_id = row.get("id")
        if not isinstance(model_id, str):
            continue
        lowered = model_id.lower()
        if accepted and not lowered.startswith(accepted):
            continue
        models.append(
            ProviderModel(
                provider_model_id=model_id,
                display_name=str(row.get("name") or row.get("display_name") or model_id),
                capabilities=["chat"],
                status="available",
                metadata={"source": source},
            )
        )
    return models


def _anthropic_headers(api_key: str) -> dict[str, str]:
    return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}


def _anthropic_chat_completion(
    base_url: str,
    model_id: str,
    messages: list[dict[str, str]],
    timeout: int,
    api_key: str | None,
    max_output_tokens: int,
) -> "tuple[str, GenerationUsage]":
    system_prompt = next(
        (item["content"] for item in messages if item.get("role") == "system"), None
    )
    conversation = [item for item in messages if item.get("role") != "system"]
    payload: dict[str, Any] = {
        "model": model_id,
        "max_tokens": max_output_tokens,
        "messages": conversation,
    }
    if system_prompt:
        payload["system"] = system_prompt
    response = _request_json(
        f"{base_url.rstrip('/')}/v1/messages",
        timeout,
        payload=payload,
        headers=_anthropic_headers(api_key or ""),
    )
    content = response.get("content")
    blocks = content if isinstance(content, list) else []
    text = " ".join(
        item.get("text", "")
        for item in blocks
        if isinstance(item, dict) and item.get("type") == "text"
    ).strip()
    if not text:
        raise ProviderUnavailableError("The model returned an empty generation response")
    return text, _anthropic_usage(response)


def _openai_chat_completion(
    base_url: str,
    model_id: str,
    messages: list[dict[str, str]],
    timeout: int,
    api_key: str | None,
    max_output_tokens: int,
) -> "tuple[str, GenerationUsage]":
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "max_completion_tokens": max_output_tokens,
        "response_format": {"type": "json_object"},
    }
    try:
        response = _request_json(
            f"{base_url.rstrip('/')}/chat/completions", timeout, api_key, payload
        )
    except ProviderUnavailableError as exc:
        if "HTTP 400" not in str(exc):
            raise
        payload.pop("response_format")
        response = _request_json(
            f"{base_url.rstrip('/')}/chat/completions", timeout, api_key, payload
        )
    return _chat_content(_first_message(response)), _openai_usage(response)


def _chat_content(message: Any) -> str:
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ProviderUnavailableError("The model returned an empty generation response")
    return content.strip()


def _first_message(response: dict[str, Any]) -> Any:
    choices = response.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    return first.get("message") if isinstance(first, dict) else None


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _openai_usage(response: dict[str, Any]) -> GenerationUsage:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {"input_tokens": None, "output_tokens": None}
    return {
        "input_tokens": _int_or_none(usage.get("input_tokens") or usage.get("prompt_tokens")),
        "output_tokens": _int_or_none(usage.get("output_tokens") or usage.get("completion_tokens")),
    }


def _anthropic_usage(response: dict[str, Any]) -> GenerationUsage:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {"input_tokens": None, "output_tokens": None}
    return {
        "input_tokens": _int_or_none(usage.get("input_tokens")),
        "output_tokens": _int_or_none(usage.get("output_tokens")),
    }


def _ollama_usage(response: dict[str, Any]) -> GenerationUsage:
    return {
        "input_tokens": _int_or_none(response.get("prompt_eval_count")),
        "output_tokens": _int_or_none(response.get("eval_count")),
    }


register_chat_completion_adapter("ollama", _ollama_chat_completion)
register_chat_completion_adapter("freetoken", _openai_compatible_chat_completion)
register_chat_completion_adapter("openrouter", _openai_compatible_chat_completion)
register_chat_completion_adapter("zai", _openai_compatible_chat_completion)
register_chat_completion_adapter("kimi", _openai_compatible_chat_completion)
register_chat_completion_adapter("anthropic", _anthropic_chat_completion)
register_chat_completion_adapter("openai", _openai_chat_completion)


def _validated_embedding(value: Any) -> list[float]:
    if not isinstance(value, list) or not value:
        raise ProviderUnavailableError("Provider returned an invalid embedding vector")
    if any(not isinstance(item, (int, float)) or not isfinite(float(item)) for item in value):
        raise ProviderUnavailableError("Provider returned an invalid embedding vector")
    return [float(item) for item in value]


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


class ZaiAdapter:
    def list_models(self, connection: ProviderCredentials, timeout: int) -> list[ProviderModel]:
        if not connection.api_key:
            raise ProviderUnavailableError("Z.ai API key is required")
        response = _request_json(
            f"{connection.base_url.rstrip('/')}/models", timeout, connection.api_key
        )
        return _catalog_chat_models(response, prefix="glm", source="catalog")

    def pull_model(
        self, connection: ProviderCredentials, model_id: str, timeout: int
    ) -> Iterator[dict[str, Any]]:
        raise ProviderUnavailableError(
            "Z.ai models are hosted remotely and cannot be downloaded"
        )


class KimiAdapter:
    def list_models(self, connection: ProviderCredentials, timeout: int) -> list[ProviderModel]:
        if not connection.api_key:
            raise ProviderUnavailableError("Kimi API key is required")
        response = _request_json(
            f"{connection.base_url.rstrip('/')}/models", timeout, connection.api_key
        )
        return _catalog_chat_models(response, prefixes=("kimi", "moonshot"), source="catalog")

    def pull_model(
        self, connection: ProviderCredentials, model_id: str, timeout: int
    ) -> Iterator[dict[str, Any]]:
        raise ProviderUnavailableError(
            "Kimi models are hosted remotely and cannot be downloaded"
        )


class OpenAIAdapter:
    def list_models(self, connection: ProviderCredentials, timeout: int) -> list[ProviderModel]:
        if not connection.api_key:
            raise ProviderUnavailableError("OpenAI API key is required")
        response = _request_json(
            f"{connection.base_url.rstrip('/')}/models", timeout, connection.api_key
        )
        return _catalog_chat_models(
            response, prefixes=("gpt-", "chatgpt-", "o1", "o3", "o4"), source="catalog"
        )

    def pull_model(
        self, connection: ProviderCredentials, model_id: str, timeout: int
    ) -> Iterator[dict[str, Any]]:
        raise ProviderUnavailableError(
            "OpenAI models are hosted remotely and cannot be downloaded"
        )


class AnthropicAdapter:
    def list_models(self, connection: ProviderCredentials, timeout: int) -> list[ProviderModel]:
        if not connection.api_key:
            raise ProviderUnavailableError("Anthropic API key is required")
        response = _request_json(
            f"{connection.base_url.rstrip('/')}/v1/models",
            timeout,
            headers=_anthropic_headers(connection.api_key),
        )
        models: list[ProviderModel] = []
        for row in _model_rows(response):
            model_id = row.get("id")
            if not isinstance(model_id, str) or not model_id.startswith("claude-"):
                continue
            models.append(
                ProviderModel(
                    provider_model_id=model_id,
                    display_name=str(row.get("display_name") or model_id),
                    capabilities=["chat"],
                    status="available",
                    metadata={"source": "catalog"},
                )
            )
        return models

    def pull_model(
        self, connection: ProviderCredentials, model_id: str, timeout: int
    ) -> Iterator[dict[str, Any]]:
        raise ProviderUnavailableError(
            "Anthropic models are hosted remotely and cannot be downloaded"
        )


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
        "zai": ModelProviderDefinition(
            adapter=ZaiAdapter(),
            default_url=config.zai_api_url,
            display_name="Z.ai",
            requires_api_key=True,
            fixed_url=True,
            sync_all_models=False,
        ),
        "kimi": ModelProviderDefinition(
            adapter=KimiAdapter(),
            default_url=config.kimi_api_url,
            display_name="Kimi (Moonshot)",
            requires_api_key=True,
            fixed_url=True,
            sync_all_models=False,
        ),
        "anthropic": ModelProviderDefinition(
            adapter=AnthropicAdapter(),
            default_url=config.anthropic_api_url,
            display_name="Anthropic",
            requires_api_key=True,
            fixed_url=True,
            sync_all_models=False,
        ),
        "openai": ModelProviderDefinition(
            adapter=OpenAIAdapter(),
            default_url=config.openai_api_url,
            display_name="OpenAI",
            requires_api_key=True,
            fixed_url=True,
            sync_all_models=False,
        ),
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
    if "capabilities" not in response:
        model_info = response.get("model_info")
        if isinstance(model_info, dict) and isinstance(model_info.get("general.architecture"), str):
            tags = model_info.get("general.tags", [])
            normalized_tags = (
                {tag.lower() for tag in tags if isinstance(tag, str)}
                if isinstance(tags, list)
                else set()
            )
            embedding_tags = {
                "feature-extraction",
                "sentence-similarity",
                "text-embedding",
            }
            capabilities.append(
                "embedding" if normalized_tags.intersection(embedding_tags) else "chat"
            )
    return capabilities


def _nested_string(value: dict[str, Any], outer: str, inner: str) -> str | None:
    nested = value.get(outer)
    result = nested.get(inner) if isinstance(nested, dict) else None
    return result if isinstance(result, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None
