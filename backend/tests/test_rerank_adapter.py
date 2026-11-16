import pytest

from app.adapter import rerank as rerank_module
from app.adapter.config import Settings
from app.adapter.rerank import HttpRerankAdapter, build_rerank_gateway
from app.domain.model_provider_entities import ProviderUnavailableError


def test_rerank_posts_contract_and_parses_results(
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
        seen["api_key"] = api_key
        return {"results": [{"index": 2, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.4}]}

    monkeypatch.setattr(rerank_module, "_request_json", fake_request_json)
    adapter = HttpRerankAdapter(
        base_url="http://localhost:8080",
        model="bge-reranker-v2-m3",
        timeout=7,
        api_key="secret",
    )
    pairs = adapter.rerank("query", ["a", "b", "c"], top_n=2)

    assert seen["url"] == "http://localhost:8080/rerank"
    assert seen["api_key"] == "secret"
    assert seen["payload"] == {
        "model": "bge-reranker-v2-m3",
        "query": "query",
        "documents": ["a", "b", "c"],
        "top_n": 2,
    }
    assert pairs == [(2, 0.9), (0, 0.4)]


def test_rerank_rejects_malformed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rerank_module, "_request_json", lambda *args, **kwargs: {"results": [{"index": "x"}]}
    )
    adapter = HttpRerankAdapter("http://localhost:8080", "m", timeout=1)
    with pytest.raises(ProviderUnavailableError):
        adapter.rerank("q", ["a"], top_n=1)


def test_rerank_propagates_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_unavailable(*args: object, **kwargs: object) -> dict:
        raise ProviderUnavailableError("Could not connect to provider")

    monkeypatch.setattr(rerank_module, "_request_json", raise_unavailable)
    adapter = HttpRerankAdapter("http://localhost:8080", "m", timeout=1)
    with pytest.raises(ProviderUnavailableError):
        adapter.rerank("q", ["a"], top_n=1)


def test_gateway_disabled_without_url() -> None:
    settings = Settings(rerank_api_url="", rerank_model="m")
    assert build_rerank_gateway(settings) is None


def test_gateway_built_from_settings() -> None:
    settings = Settings(
        rerank_api_url="http://localhost:8080",
        rerank_model="bge-reranker-v2-m3",
        rerank_api_key="secret",
    )
    gateway = build_rerank_gateway(settings)
    assert isinstance(gateway, HttpRerankAdapter)
