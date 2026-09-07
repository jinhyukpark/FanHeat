import ipaddress
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class Source(StrEnum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    X = "x"
    NEWS = "news"


class ContentType(StrEnum):
    VIDEO = "video"
    POST = "post"
    ARTICLE = "article"


class CollectionOrder(StrEnum):
    DATE = "date"
    RELEVANCE = "relevance"
    VIEW_COUNT = "viewCount"


class LanguageFilterMode(StrEnum):
    PREFER = "prefer"
    STRICT = "strict"


class Author(BaseModel):
    source_id: str | None = None
    name: str
    handle: str | None = None
    profile_url: str | None = None


class Metrics(BaseModel):
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)


class MediaContent(BaseModel):
    source: Source
    source_content_id: str
    content_type: ContentType
    author: Author
    title: str | None = None
    text: str | None = None
    url: str
    thumbnail_url: str | None = None
    published_at: datetime
    metrics: Metrics = Field(default_factory=Metrics)
    entities: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="after")
    def require_content(self) -> "MediaContent":
        if not self.title and not self.text:
            raise ValueError("title or text is required")
        return self


class NewsSourceSetting(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    domains: list[str] = Field(min_length=1, max_length=10)
    source_url: str | None = Field(default=None, max_length=2000)
    rss_url: str | None = Field(default=None, max_length=2000)
    enabled: bool = True
    allow_thumbnail_preview: bool = False

    @field_validator("domains")
    @classmethod
    def normalize_domains(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            domain = value.strip().casefold().removeprefix("www.").rstrip(".")
            if not domain or "/" in domain or ":" in domain or " " in domain:
                raise ValueError("domains must contain host names only")
            if domain not in normalized:
                normalized.append(domain)
        return normalized

    @field_validator("source_url", "rss_url")
    @classmethod
    def validate_public_source_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        url = value.strip()
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("news source URLs must be public HTTPS URLs without credentials")
        hostname = parsed.hostname.casefold().rstrip(".")
        if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
            raise ValueError("local news source URLs are not allowed")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            if not address.is_global:
                raise ValueError("private news source IP addresses are not allowed")
        return url


class CollectionRequest(BaseModel):
    source: Source
    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=25, ge=1, le=100)
    published_after: datetime | None = None
    published_before: datetime | None = None
    order: CollectionOrder = CollectionOrder.DATE
    region_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    language_code: str | None = Field(default=None, pattern=r"^[A-Za-z]{2,3}(-[A-Za-z]{2,8})?$")
    language_filter_mode: LanguageFilterMode | None = None
    news_sources: list[NewsSourceSetting] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_published_window(self) -> "CollectionRequest":
        if (
            self.published_after is not None
            and self.published_before is not None
            and self.published_after >= self.published_before
        ):
            raise ValueError("published_after must be earlier than published_before")
        return self


class CollectionResult(BaseModel):
    job_id: str
    source: Source
    status: str
    collected: int = 0
    inserted: int = 0
    updated: int = 0
    message: str | None = None


class XDriveImportRequest(BaseModel):
    collection_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    sheet_name: str | None = None
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
