import httpx

from media_collector.connectors.youtube import YouTubeConnector
from media_collector.schemas import CollectionOrder, CollectionRequest, Source


def test_youtube_search_is_enriched_with_statistics():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"items": [{"id": {"videoId": "abc"}, "snippet": {}}], "nextPageToken": "next"})
        return httpx.Response(200, json={"items": [{
            "id": "abc",
            "snippet": {
                "channelId": "channel-1", "channelTitle": "FANHEAT", "title": "BTS news",
                "description": "new video", "publishedAt": "2026-08-28T01:00:00Z",
                "thumbnails": {"high": {"url": "https://example.com/thumb.jpg"}},
            },
            "statistics": {"viewCount": "100", "likeCount": "9", "commentCount": "3"},
            "status": {"privacyStatus": "public", "embeddable": True},
        }]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    page = YouTubeConnector("test-key", client=client).collect(
        CollectionRequest(source=Source.YOUTUBE, query="BTS", order=CollectionOrder.VIEW_COUNT, region_code="KR", language_code="ko")
    )

    assert page.next_cursor == "next"
    assert page.items[0].source_content_id == "abc"
    assert page.items[0].metrics.views == 100
    assert page.items[0].author.name == "FANHEAT"
    assert requests[0].url.params["order"] == "viewCount"
    assert requests[0].url.params["maxResults"] == "50"
    assert requests[0].url.params["regionCode"] == "KR"
    assert requests[0].url.params["relevanceLanguage"] == "ko"
    assert requests[0].url.params["videoEmbeddable"] == "true"
    assert requests[1].url.params["part"] == "snippet,statistics,status"


def test_youtube_excludes_public_video_when_owner_disables_embedding():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"items": [
                {"id": {"videoId": "allowed"}, "snippet": {}},
                {"id": {"videoId": "blocked"}, "snippet": {}},
            ]})
        return httpx.Response(200, json={"items": [
            {
                "id": "allowed",
                "snippet": {
                    "channelTitle": "FANHEAT", "title": "Allowed", "description": "",
                    "publishedAt": "2026-08-28T01:00:00Z",
                },
                "statistics": {},
                "status": {"privacyStatus": "public", "embeddable": True},
            },
            {
                "id": "blocked",
                "snippet": {
                    "channelTitle": "FANHEAT", "title": "Blocked", "description": "",
                    "publishedAt": "2026-08-28T01:00:00Z",
                },
                "statistics": {},
                "status": {"privacyStatus": "public", "embeddable": False},
            },
        ]})

    page = YouTubeConnector(
        "test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    ).collect(CollectionRequest(source=Source.YOUTUBE, query="K-POP"))

    assert [item.source_content_id for item in page.items] == ["allowed"]


def test_youtube_excludes_private_or_missing_status_video():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"items": [
                {"id": {"videoId": "private"}, "snippet": {}},
                {"id": {"videoId": "unknown"}, "snippet": {}},
            ]})
        return httpx.Response(200, json={"items": [
            {"id": "private", "status": {"privacyStatus": "private", "embeddable": True}},
            {"id": "unknown"},
        ]})

    page = YouTubeConnector(
        "test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    ).collect(CollectionRequest(source=Source.YOUTUBE, query="K-POP"))

    assert page.items == []
