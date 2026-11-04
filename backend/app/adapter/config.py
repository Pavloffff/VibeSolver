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


@lru_cache
def get_settings() -> Settings:
    return Settings()
