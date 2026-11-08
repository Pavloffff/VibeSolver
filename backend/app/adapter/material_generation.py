from app.adapter.model_providers.providers import complete_json, embed_texts
from app.domain.model_provider_entities import ProviderCredentials


class MaterialGenerationAdapter:
    def embed_queries(
        self,
        credentials: ProviderCredentials,
        model_id: str,
        queries: list[str],
        timeout: int,
    ) -> list[list[float]]:
        return embed_texts(
            credentials.provider_type,
            credentials.base_url,
            model_id,
            queries,
            timeout,
            credentials.api_key,
        )

    def generate_json(
        self,
        credentials: ProviderCredentials,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        timeout: int,
        max_output_tokens: int,
    ) -> str:
        return complete_json(
            credentials.provider_type,
            credentials.base_url,
            model_id,
            system_prompt,
            user_prompt,
            timeout,
            credentials.api_key,
            max_output_tokens,
        )
