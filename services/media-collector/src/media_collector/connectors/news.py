import hashlib
from calendar import timegm
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

from media_collector.schemas import Author, CollectionRequest, ContentType, MediaContent, Source

from .base import Connector, ConnectorConfigurationError, ConnectorError, ConnectorPage, ConnectorTransientError


class NewsConnector(Connector):
    news_api_url = "https://newsapi.org/v2/everything"

    def __init__(
        self,
        api_key: str | None,
        rss_feeds: list[str] | None = None,
        timeout: float = 20,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.rss_feeds = rss_feeds or []
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def collect(self, request: CollectionRequest, cursor: str | None = None) -> ConnectorPage:
        if self.api_key:
            return self._collect_api(request, cursor)
        if self.rss_feeds:
            return self._collect_rss(request)
        raise ConnectorConfigurationError("NEWS_API_KEY or NEWS_RSS_FEEDS must be configured")

    def _collect_api(self, request: CollectionRequest, cursor: str | None) -> ConnectorPage:
        page = int(cursor or "1")
        params: dict[str, Any] = {
            "q": request.query,
            "pageSize": min(request.max_results, 100),
            "page": page,
            "sortBy": "publishedAt",
            "apiKey": self.api_key,
        }
        if request.published_after:
            params["from"] = request.published_after.isoformat()
        response = self.client.get(self.news_api_url, params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code == 429 or response.status_code >= 500:
                raise ConnectorTransientError(f"News API {response.status_code}: {response.text}") from exc
            raise ConnectorError(f"News API {response.status_code}: {response.text}") from exc
        payload = response.json()
        items = [self._normalize_article(article) for article in payload.get("articles", []) if article.get("url")]
        next_cursor = str(page + 1) if page * request.max_results < payload.get("totalResults", 0) else None
        return ConnectorPage(items=items, next_cursor=next_cursor)

    def _collect_rss(self, request: CollectionRequest) -> ConnectorPage:
        terms = request.query.casefold().split()
        items: list[MediaContent] = []
        for url in self.rss_feeds:
            response = self.client.get(url)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            source_name = feed.feed.get("title", url)
            for entry in feed.entries:
                haystack = f"{entry.get('title', '')} {entry.get('summary', '')}".casefold()
                if terms and not all(term in haystack for term in terms):
                    continue
                item = self._normalize_feed_entry(entry, source_name)
                if not request.published_after or item.published_at >= request.published_after:
                    items.append(item)
                if len(items) >= request.max_results:
                    return ConnectorPage(items=items)
        return ConnectorPage(items=items)

    @staticmethod
    def _normalize_article(article: dict[str, Any]) -> MediaContent:
        return MediaContent(
            source=Source.NEWS,
            source_content_id=hashlib.sha256(article["url"].encode()).hexdigest(),
            content_type=ContentType.ARTICLE,
            author=Author(name=article.get("source", {}).get("name") or article.get("author") or "Unknown"),
            title=article.get("title"), text=article.get("description"), url=article["url"],
            thumbnail_url=article.get("urlToImage"),
            published_at=datetime.fromisoformat(article["publishedAt"].replace("Z", "+00:00")), raw=article,
        )

    @staticmethod
    def _normalize_feed_entry(entry: Any, source_name: str) -> MediaContent:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at = datetime.fromtimestamp(timegm(published), timezone.utc) if published else datetime.now(timezone.utc)
        url = entry.get("link")
        return MediaContent(
            source=Source.NEWS,
            source_content_id=entry.get("id") or hashlib.sha256(url.encode()).hexdigest(),
            content_type=ContentType.ARTICLE,
            author=Author(name=source_name), title=entry.get("title"), text=entry.get("summary"),
            url=url, published_at=published_at, raw=dict(entry),
        )
