import httpx

from media_collector.connectors.news import NewsConnector
from media_collector.connectors.x import XConnector
from media_collector.schemas import CollectionRequest, NewsSourceSetting, Source


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


def test_news_rss_sends_feed_compatible_headers():
    captured_headers = {}

    def transport(request):
        captured_headers.update(request.headers)
        return httpx.Response(200, content=b'<rss version="2.0"><channel /></rss>')

    client = httpx.Client(transport=httpx.MockTransport(transport))
    NewsConnector(None, ["https://example.com/feed"], client=client).collect(
        CollectionRequest(source=Source.NEWS, query="IVE")
    )

    assert "FANHEATBot" in captured_headers["user-agent"]
    assert "application/rss+xml" in captured_headers["accept"]


def test_news_api_allowlist_filters_publishers_and_requires_thumbnail_opt_in():
    payload = {"totalResults": 2, "articles": [
        {"source": {"name": "Allowed"}, "title": "IVE showcase", "description": "News",
         "url": "https://news.example.com/ive", "urlToImage": "https://cdn.example.com/ive.jpg",
         "publishedAt": "2026-09-06T02:00:00Z"},
        {"source": {"name": "Blocked"}, "title": "IVE rumor", "description": "News",
         "url": "https://blocked.example/ive", "urlToImage": "https://blocked.example/ive.jpg",
         "publishedAt": "2026-09-06T02:00:00Z"},
    ]}
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    request = CollectionRequest(source=Source.NEWS, query="IVE", news_sources=[
        NewsSourceSetting(name="Allowed", domains=["example.com"], allow_thumbnail_preview=False)
    ])

    page = NewsConnector("token", client=client).collect(request)

    assert [item.url for item in page.items] == ["https://news.example.com/ive"]
    assert page.items[0].thumbnail_url is None
    assert page.items[0].raw["fanheat_link_policy"]["article_link_only"] is True


def test_news_rss_uses_configured_feed_and_explicit_thumbnail_permission(monkeypatch):
    rss = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:media="http://search.yahoo.com/mrss/" version="2.0"><channel><title>Official Feed</title>
      <item><guid>article-1</guid><title>IVE showcase</title><description>Photo article</description>
      <link>https://ent.example.com/ive</link><media:thumbnail url="https://ent.example.com/thumb.jpg" />
      <pubDate>Sun, 06 Sep 2026 02:00:00 GMT</pubDate></item>
    </channel></rss>"""
    requested_urls = []
    monkeypatch.setattr(
        "media_collector.connectors.news.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: (requested_urls.append(str(request.url)) or httpx.Response(200, content=rss))
    ))
    request = CollectionRequest(source=Source.NEWS, query="IVE", news_sources=[NewsSourceSetting(
        name="Example Entertainment", domains=["ent.example.com"],
        rss_url="https://feeds.example.com/ent.xml", allow_thumbnail_preview=True,
    )])

    page = NewsConnector("token", ["https://legacy.example/feed"], client=client).collect(request)

    assert requested_urls == ["https://feeds.example.com/ent.xml"]
    assert page.items[0].thumbnail_url == "https://ent.example.com/thumb.jpg"


def test_news_open_graph_source_discovers_articles_without_rss(monkeypatch):
    listing = """<html><body>
      <a href="/news/ive-comeback">아이브 컴백 소식</a>
      <a href="/about">회사 소개</a>
    </body></html>"""
    article = """<html><head>
      <meta property="og:title" content="아이브 컴백 쇼케이스">
      <meta property="og:description" content="아이브 컴백 무대를 공개했다.">
      <meta property="og:image" content="/images/ive.jpg">
      <meta property="article:published_time" content="2026-09-06T11:00:00+09:00">
    </head></html>"""

    monkeypatch.setattr(
        "media_collector.connectors.news.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )

    def transport(request):
        if request.url.path == "/entertainment":
            return httpx.Response(200, headers={"content-type": "text/html"}, text=listing)
        if request.url.path == "/news/ive-comeback":
            return httpx.Response(200, headers={"content-type": "text/html"}, text=article)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(transport), follow_redirects=True)
    request = CollectionRequest(source=Source.NEWS, query="아이브 컴백", news_sources=[NewsSourceSetting(
        name="스타뉴스",
        domains=["star.example.com"],
        source_url="https://star.example.com/entertainment",
        allow_thumbnail_preview=True,
    )])

    page = NewsConnector(None, client=client).collect(request)

    assert len(page.items) == 1
    assert page.items[0].title == "아이브 컴백 쇼케이스"
    assert page.items[0].url == "https://star.example.com/news/ive-comeback"
    assert page.items[0].thumbnail_url == "https://star.example.com/images/ive.jpg"
    assert page.items[0].raw["fanheat_link_policy"]["discovery_origin"] == "publisher_page"


def test_naver_news_uses_original_article_link_and_open_graph_thumbnail(monkeypatch):
    payload = {"total": 2, "items": [
        {"title": "<b>아이브</b> 쇼케이스", "description": "새 앨범 &amp; 무대",
         "originallink": "https://star.example.com/news/1", "link": "https://n.news.naver.com/1",
         "pubDate": "Sun, 06 Sep 2026 11:00:00 +0900"},
        {"title": "아이브 소식", "description": "허용하지 않은 매체",
         "originallink": "https://blocked.example/news/2", "link": "https://n.news.naver.com/2",
         "pubDate": "Sun, 06 Sep 2026 10:00:00 +0900"},
    ]}
    def transport(request):
        if request.url.host == "openapi.naver.com":
            return httpx.Response(200, json=payload)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text='<html><head><meta property="og:image" content="/images/ive.jpg"></head></html>',
        )

    monkeypatch.setattr(
        "media_collector.connectors.news.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )
    client = httpx.Client(transport=httpx.MockTransport(transport), follow_redirects=True)
    request = CollectionRequest(source=Source.NEWS, query="아이브", region_code="KR", news_sources=[
        NewsSourceSetting(name="스타뉴스", domains=["star.example.com"], allow_thumbnail_preview=True)
    ])

    page = NewsConnector(
        None,
        client=client,
        naver_client_id="id",
        naver_client_secret="secret",
        naver_api_provider="developers",
    ).collect(request)

    assert len(page.items) == 1
    assert page.items[0].url == "https://star.example.com/news/1"
    assert page.items[0].title == "아이브 쇼케이스"
    assert page.items[0].text == "새 앨범 & 무대"
    assert page.items[0].thumbnail_url == "https://star.example.com/images/ive.jpg"
    assert page.items[0].raw["fanheat_link_policy"]["thumbnail_origin"] == "open_graph"
    assert page.items[0].raw["fanheat_link_policy"]["naver_result_url"] == "https://n.news.naver.com/1"


def test_naver_search_takes_priority_over_configured_publisher_feed():
    requested_hosts = []
    payload = {"total": 1, "items": [{
        "title": "아이브 컴백",
        "description": "새 앨범 공개",
        "originallink": "https://news.example.com/article/1",
        "link": "https://n.news.naver.com/article/1",
        "pubDate": "Sun, 06 Sep 2026 11:00:00 +0900",
    }]}

    def transport(request):
        requested_hosts.append(request.url.host)
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    request = CollectionRequest(source=Source.NEWS, query="아이브", region_code="KR", news_sources=[
        NewsSourceSetting(
            name="Example News",
            domains=["example.com"],
            rss_url="https://feeds.example.com/entertainment.xml",
        )
    ])

    page = NewsConnector(
        None,
        client=client,
        naver_client_id="client-id",
        naver_client_secret="client-secret",
        naver_api_provider="developers",
    ).collect(request)

    assert requested_hosts == ["openapi.naver.com"]
    assert len(page.items) == 1


def test_naver_api_hub_uses_cloud_endpoint_and_headers():
    captured = {}
    payload = {"total": 1, "items": [{
        "title": "아이브 컴백",
        "description": "새 앨범 공개",
        "originallink": "https://news.example.com/article/1",
        "link": "https://n.news.naver.com/article/1",
        "pubDate": "Sun, 06 Sep 2026 11:00:00 +0900",
    }]}

    def transport(request):
        captured["request"] = request
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    page = NewsConnector(
        None,
        client=client,
        naver_client_id="cloud-id",
        naver_client_secret="cloud-secret",
        naver_api_provider="api_hub",
    ).collect(CollectionRequest(source=Source.NEWS, query="아이브", region_code="KR"))

    request = captured["request"]
    assert request.url.host == "naverapihub.apigw.ntruss.com"
    assert request.url.params["format"] == "json"
    assert request.headers["X-NCP-APIGW-API-KEY-ID"] == "cloud-id"
    assert request.headers["X-NCP-APIGW-API-KEY"] == "cloud-secret"
    assert len(page.items) == 1


def test_naver_news_rejects_semantic_results_without_literal_query_match():
    payload = {"total": 3, "items": [
        {
            "title": "인도네시아 화산 폭발…항공편 결항",
            "description": "공항 여섯 곳의 운영이 중단됐다.",
            "originallink": "https://news.example.com/volcano",
            "link": "https://n.news.naver.com/volcano",
            "pubDate": "Sun, 06 Sep 2026 11:00:00 +0900",
        },
        {
            "title": "아이브, 신곡 무대 공개",
            "description": "걸그룹 아이브가 새 앨범으로 돌아왔다.",
            "originallink": "https://news.example.com/ive",
            "link": "https://n.news.naver.com/ive",
            "pubDate": "Sun, 06 Sep 2026 10:00:00 +0900",
        },
        {
            "title": "아이돌 신곡 발표",
            "description": "새 앨범 소식",
            "originallink": "https://news.example.com/idol",
            "link": "https://n.news.naver.com/idol",
            "pubDate": "Sun, 06 Sep 2026 09:00:00 +0900",
        },
    ]}
    captured = {}

    def transport(request):
        captured["display"] = request.url.params["display"]
        return httpx.Response(200, json=payload)

    page = NewsConnector(
        None,
        client=httpx.Client(transport=httpx.MockTransport(transport)),
        naver_client_id="id",
        naver_client_secret="secret",
    ).collect(CollectionRequest(source=Source.NEWS, query="아이돌 신곡", region_code="KR", max_results=10))

    assert captured["display"] == "50"
    assert [item.url for item in page.items] == ["https://news.example.com/idol"]


def test_ambiguous_airport_query_requires_kpop_context():
    assert NewsConnector._matches_query(
        "공항", "인도네시아 화산 폭발", "공항 여섯 곳의 운영이 중단됐다."
    ) is False
    assert NewsConnector._matches_query(
        "공항", "아이돌 공항 출국길", "걸그룹 멤버들이 팬들에게 인사했다."
    ) is True
    assert NewsConnector._matches_query(
        "공항", "아이돌 멤버 근황", "지난해 공항에서 팬들에게 인사했다."
    ) is False


def test_news_query_requires_a_title_anchor_not_only_a_description_mention():
    assert NewsConnector._matches_query(
        "아이돌 인터뷰", "손흥민, 경기에서 맹활약", "방송에서 아이돌 인터뷰도 소개했다."
    ) is False
    assert NewsConnector._matches_query(
        "아이돌 인터뷰", "아이돌이 직접 밝힌 컴백 소감", "단독 인터뷰에서 새 앨범을 소개했다."
    ) is True


def test_ambiguous_airport_query_is_expanded_before_naver_search():
    captured = {}

    def transport(request):
        captured["query"] = request.url.params["query"]
        return httpx.Response(200, json={"total": 0, "items": []})

    NewsConnector(
        None,
        client=httpx.Client(transport=httpx.MockTransport(transport)),
        naver_client_id="id",
        naver_client_secret="secret",
    ).collect(CollectionRequest(source=Source.NEWS, query="공항", region_code="KR"))

    assert captured["query"] == "아이돌 공항"


def test_open_graph_thumbnail_rejects_redirect_outside_allowed_publisher(monkeypatch):
    monkeypatch.setattr(
        "media_collector.connectors.news.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )

    def transport(request):
        if request.url.host == "news.example.com":
            return httpx.Response(302, headers={"location": "https://tracking.example.net/article"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text='<meta property="og:image" content="https://cdn.example.net/thumb.jpg">',
        )

    client = httpx.Client(transport=httpx.MockTransport(transport), follow_redirects=True)
    source = NewsSourceSetting(name="Allowed", domains=["example.com"], allow_thumbnail_preview=True)

    assert NewsConnector("token", client=client)._open_graph_thumbnail(
        "https://news.example.com/article", source
    ) is None
