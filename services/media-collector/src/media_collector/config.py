from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./media_collector.db"
    redis_url: str = "redis://localhost:6379/0"
    youtube_api_key: str | None = None
    x_bearer_token: str | None = None
    news_api_key: str | None = None
    news_rss_feeds: str = ""
    naver_client_id: str | None = None
    naver_client_secret: str | None = None
    naver_api_provider: Literal["developers", "api_hub"] = "api_hub"
    request_timeout_seconds: float = Field(default=20, gt=0)
    max_results_per_request: int = Field(default=25, ge=1, le=100)
    internal_api_key: str | None = None
    collector_admin_user: str = "fanheat"
    collector_admin_password: str | None = None
    ai_worker_url: str = "http://localhost:8090"
    n8n_webhook_url: str = "http://localhost:5678/webhook/fanheat-full-pipeline"
    n8n_x_webhook_url: str = "http://localhost:5678/webhook/fanheat-x-pipeline"
    n8n_artist_webhook_url: str = "http://localhost:5678/webhook/fanheat-artist-import"
    n8n_health_url: str = "http://localhost:5678/healthz"
    n8n_api_key: str | None = None

    @property
    def rss_feeds(self) -> list[str]:
        return [item.strip() for item in self.news_rss_feeds.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
