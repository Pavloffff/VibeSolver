from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIBESOLVER_")

    database_url: str = "postgresql://vibesolver:vibesolver@localhost:5432/vibesolver"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str = "http://localhost:8333"
    s3_access_key: str = "vibesolver"
    s3_secret_key: str = "vibesolver"
    s3_bucket_raw: str = "raw"
    cors_origins: list[str] = ["*"]
    max_upload_bytes: int = 500 * 1024 * 1024
    max_archive_unpacked_bytes: int = 2 * 1024 * 1024 * 1024
    model_secrets_key: str | None = None
    provider_request_timeout_seconds: int = 20
    material_generation_timeout_seconds: int = 180
    material_generation_max_output_tokens: int = 8192
    material_generation_context_chunks: int = 24
    material_generation_max_context_characters: int = 48_000
    material_generation_max_files: int = 12
    material_generation_max_file_bytes: int = 200_000
    material_generation_max_total_bytes: int = 1_000_000
    freetoken_api_url: str = "http://host.docker.internal:1920/v1"
    ollama_api_url: str = "http://host.docker.internal:11434"
    openrouter_api_url: str = "https://openrouter.ai/api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
