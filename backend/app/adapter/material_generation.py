from app.adapter.model_providers.providers import (
    complete_json,
    complete_json_with_usage,
    embed_texts,
)
from app.domain.model_provider_entities import ProviderCredentials
from app.domain.repositories.material_generation import GeneratedJson


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

    def generate_json_with_usage(
        self,
        credentials: ProviderCredentials,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        timeout: int,
        max_output_tokens: int,
    ) -> GeneratedJson:
        text, usage = complete_json_with_usage(
            credentials.provider_type,
            credentials.base_url,
            model_id,
            system_prompt,
            user_prompt,
            timeout,
            credentials.api_key,
            max_output_tokens,
        )
        return GeneratedJson(
            text=text,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
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
