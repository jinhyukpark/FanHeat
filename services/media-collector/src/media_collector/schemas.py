from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator


class Source(StrEnum):
    YOUTUBE = "youtube"
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


class CollectionRequest(BaseModel):
    source: Source
    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=25, ge=1, le=100)
    published_after: datetime | None = None
    order: CollectionOrder = CollectionOrder.DATE
    region_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    language_code: str | None = Field(default=None, pattern=r"^[A-Za-z]{2,3}(-[A-Za-z]{2,8})?$")
    language_filter_mode: LanguageFilterMode | None = None


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
