from app.adapter.config import Settings
from app.adapter.model_providers.providers import _request_json
from app.domain.model_provider_entities import ProviderUnavailableError
from app.domain.repositories.retrieval import RerankGateway


class HttpRerankAdapter:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: int,
        api_key: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._api_key = api_key

    def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        response = _request_json(
            f"{self._base_url}/rerank",
            self._timeout,
            self._api_key,
            {
                "model": self._model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
            },
        )
        rows = response.get("results")
        if not isinstance(rows, list):
            raise ProviderUnavailableError("Rerank service returned an invalid response")
        pairs: list[tuple[int, float]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            index = row.get("index")
            score = row.get("relevance_score")
            if not isinstance(index, int) or not isinstance(score, (int, float)):
                raise ProviderUnavailableError(
                    "Rerank service returned an invalid response"
                )
            pairs.append((index, float(score)))
        if not pairs:
            raise ProviderUnavailableError("Rerank service returned no results")
        return pairs


def build_rerank_gateway(settings: Settings) -> RerankGateway | None:
    if not settings.rerank_api_url or not settings.rerank_model:
        return None
    return HttpRerankAdapter(
        base_url=settings.rerank_api_url,
        model=settings.rerank_model,
        timeout=settings.rerank_timeout_seconds,
        api_key=settings.rerank_api_key,
    )
