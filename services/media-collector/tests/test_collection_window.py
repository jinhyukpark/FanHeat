from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from media_collector.admin import AdminCollectionRequest, collection_window
from media_collector.schemas import CollectionRequest, Source


def test_news_collection_dates_become_inclusive_korean_calendar_window():
    request = AdminCollectionRequest(
        source=Source.NEWS,
        queries=["아이브"],
        published_from=date(2026, 9, 1),
        published_to=date(2026, 9, 2),
        published_within_hours=None,
    )

    published_after, published_before = collection_window(request)

    assert published_after == datetime(2026, 8, 31, 15, tzinfo=timezone.utc)
    assert published_before == datetime(2026, 9, 2, 15, tzinfo=timezone.utc)


def test_news_collection_rejects_reversed_date_range():
    with pytest.raises(ValidationError, match="시작일은 종료일보다 늦을 수 없습니다"):
        AdminCollectionRequest(
            source=Source.NEWS,
            queries=["아이브"],
            published_from=date(2026, 9, 2),
            published_to=date(2026, 9, 1),
        )


def test_collection_request_rejects_empty_half_open_window():
    boundary = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="published_after must be earlier"):
        CollectionRequest(
            source=Source.NEWS,
            query="아이브",
            published_after=boundary,
            published_before=boundary,
        )
