import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .schemas import utc_now


def uuid_text() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class CollectionJob(Base):
    __tablename__ = "media_collection_jobs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_text)
    source: Mapped[str] = mapped_column(String(32), index=True)
    query: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    cursor: Mapped[str | None] = mapped_column(Text)
    collected_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class CollectionRule(Base):
    __tablename__ = "media_collection_rules"
    __table_args__ = (UniqueConstraint("source", "query", "artist_id", name="media_collection_rules_source_query_artist_key"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_text)
    artist_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    query: Mapped[str] = mapped_column(String(500))
    interval_seconds: Mapped[int] = mapped_column(Integer, default=600)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_collect_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class CollectorSettings(Base):
    __tablename__ = "media_collector_settings"

    singleton: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=True)
    region_code: Mapped[str] = mapped_column(String(2), default="KR")
    language_code: Mapped[str] = mapped_column(String(10), default="ko")
    language_filter_mode: Mapped[str] = mapped_column(String(16), default="strict")
    content_tone: Mapped[str] = mapped_column(String(32), default="fan_20s")
    target_audience: Mapped[str] = mapped_column(String(32), default="general_fans")
    body_lines: Mapped[int] = mapped_column(Integer, default=4)
    emoji_level: Mapped[str] = mapped_column(String(16), default="light")
    hashtag_count: Mapped[int] = mapped_column(Integer, default=5)
    ai_comment_min_count: Mapped[int] = mapped_column(Integer, default=5)
    ai_comment_max_count: Mapped[int] = mapped_column(Integer, default=30)
    news_sources: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class RawMedia(Base):
    __tablename__ = "media_raw_items"
    __table_args__ = (UniqueConstraint("source", "source_content_id", name="uq_media_raw_source_content"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_text)
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_content_id: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    first_collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MediaItem(Base):
    __tablename__ = "media_items"
    __table_args__ = (
        UniqueConstraint("source", "source_content_id", name="uq_media_item_source_content"),
        Index("ix_media_items_published_source", "published_at", "source"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_text)
    raw_item_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("media_raw_items.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_content_id: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(32))
    author: Mapped[dict] = mapped_column(JSON)
    title: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    entities: Mapped[list] = mapped_column(JSON, default=list)
    enrichment_status: Mapped[str] = mapped_column(String(32), default="pending")
    enrichment: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    snapshots: Mapped[list["MetricSnapshot"]] = relationship(cascade="all, delete-orphan")


class MetricSnapshot(Base):
    __tablename__ = "media_metric_snapshots"
    __table_args__ = (Index("ix_metric_item_captured", "media_item_id", "captured_at"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_text)
    media_item_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("media_items.id", ondelete="CASCADE"), index=True)
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
