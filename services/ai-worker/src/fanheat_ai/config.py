from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./fanheat_ai.db"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    llm_timeout_seconds: float = Field(default=120, gt=0)
    pipeline_batch_size: int = Field(default=5, ge=1, le=50)
    prompt_version: str = "fanheat-v1"
    internal_api_key: str | None = None
    auto_approve_low_risk: bool = False
    comment_min_delay_minutes: int = Field(default=5, ge=1, le=1440)
    comment_max_delay_minutes: int = Field(default=30, ge=1, le=1440)


@lru_cache
def get_settings() -> Settings:
    return Settings()
