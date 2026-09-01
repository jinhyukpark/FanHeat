import httpx

from media_collector.connectors.news import NewsConnector
from media_collector.connectors.x import XConnector
from media_collector.schemas import CollectionRequest, Source


def test_x_recent_search_maps_metrics_and_cursor():
    payload = {
        "data": [{
            "id": "42", "author_id": "7", "text": "BTS comeback",
            "created_at": "2026-08-28T02:00:00Z",
            "public_metrics": {"like_count": 11, "reply_count": 2, "retweet_count": 4},
        }],
        "includes": {"users": [{"id": "7", "name": "Fan", "username": "fanheat"}]},
        "meta": {"next_token": "cursor-2"},
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json=payload, headers={"x-rate-limit-remaining": "99", "x-rate-limit-reset": "12345"}
    )))

    page = XConnector("token", client=client).collect(CollectionRequest(source=Source.X, query="BTS"))

    assert page.next_cursor == "cursor-2"
    assert page.rate_limit_remaining == 99
    assert page.items[0].metrics.shares == 4
    assert page.items[0].author.handle == "fanheat"


def test_news_rss_filters_and_normalizes_entries():
    rss = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>K-pop News</title>
      <item><guid>article-1</guid><title>BTS announces a new album</title>
      <description>Release details</description><link>https://example.com/bts</link>
      <pubDate>Fri, 28 Aug 2026 02:00:00 GMT</pubDate></item>
      <item><guid>article-2</guid><title>Unrelated story</title>
      <description>Other news</description><link>https://example.com/other</link></item>
    </channel></rss>"""
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=rss)))

    page = NewsConnector(None, ["https://example.com/feed"], client=client).collect(
        CollectionRequest(source=Source.NEWS, query="BTS")
    )

    assert len(page.items) == 1
    assert page.items[0].source_content_id == "article-1"
    assert page.items[0].author.name == "K-pop News"
