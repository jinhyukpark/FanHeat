from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class EnrichmentResult(BaseModel):
    language: str = "ko"
    artist: str | None = None
    topic: str
    sentiment: Literal["positive", "neutral", "negative", "mixed"]
    toxicity: float = Field(ge=0, le=1)
    importance: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1, max_length=1000)
    publish_recommendation: Literal["publish", "review", "reject"]
    confidence: float = Field(ge=0, le=1)


class DraftContent(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=10)
    risk_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value):
        """Store tag names without a display prefix and drop duplicates."""
        if not isinstance(value, list):
            return value
        normalized = []
        seen = set()
        for raw_tag in value:
            tag = str(raw_tag).strip().lstrip("#").strip()
            if not tag or tag.casefold() in seen:
                continue
            seen.add(tag.casefold())
            normalized.append(tag)
        return normalized


class PostGenerationContent(BaseModel):
    analysis: EnrichmentResult
    draft: DraftContent | None = None

    @model_validator(mode="after")
    def require_draft_for_publishable_content(self):
        if self.analysis.publish_recommendation != "reject" and self.draft is None:
            raise ValueError("draft is required unless publish_recommendation is reject")
        return self


class CommentContent(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    risk_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class PipelineRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=50)
    create_drafts: bool = True
    media_ids: list[str] | None = Field(default=None, min_length=1, max_length=50)
    source: Literal["youtube", "x", "news"] | None = None
    priority: Literal["manual", "background"] = "background"


class PipelineResult(BaseModel):
    processed: int
    drafts_created: int
    skipped: int = 0
    failed: int
    item_ids: list[str]
    errors: list[dict[str, str]] = Field(default_factory=list)
    deferred: bool = False
    deferred_reason: str | None = None


class ReviewRequest(BaseModel):
    reviewed_by: str | None = None
    scheduled_at: datetime | None = None
    approval_source: Literal["admin_manual", "admin_bulk", "n8n", "auto_policy"] = "n8n"


class RejectionRequest(BaseModel):
    reviewed_by: str | None = None
    reason: str = Field(min_length=1, max_length=1000)


class PublishRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)
    draft_ids: list[str] | None = Field(default=None, min_length=1, max_length=50)


class PublishResult(BaseModel):
    published_posts: int
    published_comments: int
    comment_drafts_created: int
    engagement_plans_created: int = 0
    engagement_actions_completed: int = 0
    skipped: int
    failed: int
    requested: int = 0
    selected: int = 0
    outcomes: list[dict[str, str]] = Field(default_factory=list)


class EngagementRunRequest(BaseModel):
    limit: int = Field(default=30, ge=1, le=100)


class EngagementRunResult(BaseModel):
    plans_created: int
    comments_published: int
    post_heats_completed: int
    comment_likes_completed: int
    actions_failed: int
    plans_cancelled_for_human_comments: int
    deferred: bool = False
    deferred_reason: str | None = None


class OllamaChatResponse(BaseModel):
    message: dict[str, Any]
