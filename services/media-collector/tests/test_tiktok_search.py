import httpx
import pytest
from media_collector.connectors.tiktok_search import TikTokSearchConnector
from media_collector.connectors.base import ConnectorTransientError
from media_collector.schemas import CollectionRequest, Source

URL = "https://www.tiktok.com/@ive.official/video/7420000000000000001"

def test_search_only_embeds_valid_unique_urls_and_keeps_unknown_metrics():
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.host == "openapi.naver.com":
            return httpx.Response(200, json={"items": [{"link": link} for link in [
                URL, URL, "https://www.tiktok.com.evil.test/@a/video/7420000000000000001",
                "https://www.tiktok.com/@a/video/7420000000000000002"]]})
        assert "x-naver-client-secret" not in request.headers
        if request.url.params["url"].endswith("2"):
            return httpx.Response(404)
        return httpx.Response(200, json={"type": "video", "provider_name": "TikTok", "title": "IVE", "html": "untrusted"})
    connector = TikTokSearchConnector("id", "secret", client=httpx.Client(transport=httpx.MockTransport(handler)))
    page = connector.collect(CollectionRequest(source=Source.TIKTOK, query="IVE", max_results=10))
    assert len(page.items) == 1
    assert len(calls) == 3
    assert page.items[0].metrics.views is None
    assert page.items[0].raw["timestamp_basis"] == "discovered_at"
    assert "html" not in page.items[0].raw

def test_rate_limit_is_not_reported_as_empty_collection():
    connector = TikTokSearchConnector("id", "secret", client=httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(429))))
    with pytest.raises(ConnectorTransientError):
        connector.collect(CollectionRequest(source=Source.TIKTOK, query="IVE"))

@pytest.mark.parametrize("url", ["http://www.tiktok.com/@a/video/7420000000000000001", "https://x@www.tiktok.com/@a/video/7420000000000000001", "https://www.tiktok.com:999/@a/video/7420000000000000001", "https://127.0.0.1/video/7420000000000000001"])
def test_untrusted_urls(url):
    assert TikTokSearchConnector.video_url(url) is None
