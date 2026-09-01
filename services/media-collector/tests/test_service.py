from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from media_collector.connectors.base import Connector, ConnectorPage
from media_collector.models import Base, MediaItem, MetricSnapshot, RawMedia
from media_collector.schemas import Author, CollectionRequest, ContentType, MediaContent, Metrics, Source
from media_collector.service import CollectionService


class StubConnector(Connector):
    def collect(self, request, cursor=None):
        return ConnectorPage(items=[MediaContent(
            source=request.source, source_content_id="same-id", content_type=ContentType.VIDEO,
            author=Author(name="artist"), title="video", url="https://example.com/video",
            published_at=datetime(2026, 8, 28, tzinfo=timezone.utc), metrics=Metrics(views=10),
            raw={"id": "same-id", "viewCount": 10},
        )])


class StubRegistry:
    def get(self, source):
        return StubConnector()


def test_collection_deduplicates_content_but_keeps_metric_history():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    request = CollectionRequest(source=Source.YOUTUBE, query="BTS")
    with Session(engine, expire_on_commit=False) as session:
        service = CollectionService(session, StubRegistry())
        first = service.run(request)
        second = service.run(request)

        assert first.inserted == 1
        assert second.updated == 1
        assert session.scalar(select(func.count()).select_from(MediaItem)) == 1
        assert session.scalar(select(func.count()).select_from(RawMedia)) == 1
        assert session.scalar(select(func.count()).select_from(MetricSnapshot)) == 2
