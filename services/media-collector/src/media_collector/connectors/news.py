import hashlib
import ipaddress
import re
import socket
from calendar import timegm
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from media_collector.schemas import Author, CollectionRequest, ContentType, MediaContent, NewsSourceSetting, Source

from .base import Connector, ConnectorConfigurationError, ConnectorError, ConnectorPage, ConnectorTransientError


class NewsConnector(Connector):
    news_api_url = "https://newsapi.org/v2/everything"
    naver_api_url = "https://openapi.naver.com/v1/search/news.json"
    naver_api_hub_url = "https://naverapihub.apigw.ntruss.com/search/v1/news"
    open_graph_max_bytes = 1_500_000
    _ambiguous_query_expansions = {
        "공항": "아이돌 공항",
        "패션": "아이돌 패션",
        "인터뷰": "가수 인터뷰",
        "차트": "음원 차트",
        "뉴스": "K-POP 뉴스",
        "사진": "아이돌 사진",
        "영상": "아이돌 영상",
    }
    _ambiguous_title_anchors = {
        "공항": ("공항", "출국", "입국"),
        "패션": ("패션", "스타일", "룩"),
        "인터뷰": ("인터뷰", "대담"),
        "차트": ("차트", "순위", "1위"),
        "뉴스": ("kpop", "케이팝", "아이돌"),
        "사진": ("사진", "포토", "화보"),
        "영상": ("영상", "비디오", "티저"),
    }

    def __init__(
        self,
        api_key: str | None,
        rss_feeds: list[str] | None = None,
        timeout: float = 20,
        client: httpx.Client | None = None,
        naver_client_id: str | None = None,
        naver_client_secret: str | None = None,
        naver_api_provider: str = "api_hub",
    ):
        self.api_key = api_key
        self.rss_feeds = rss_feeds or []
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self.naver_client_id = naver_client_id
        self.naver_client_secret = naver_client_secret
        self.naver_api_provider = naver_api_provider

    def collect(self, request: CollectionRequest, cursor: str | None = None) -> ConnectorPage:
        if self.naver_client_id and self.naver_client_secret and request.region_code in (None, "KR"):
            return self._collect_naver(request, cursor)
        if any(source.enabled and (source.rss_url or source.source_url) for source in request.news_sources):
            return self._collect_configured_sources(request)
        if self.api_key:
            return self._collect_api(request, cursor)
        if self.rss_feeds:
            return self._collect_rss(request)
        raise ConnectorConfigurationError("NAVER_CLIENT_ID/SECRET, NEWS_API_KEY, or NEWS_RSS_FEEDS must be configured")

    def _collect_naver(self, request: CollectionRequest, cursor: str | None) -> ConnectorPage:
        start = int(cursor or "1")
        fetch_size = min(request.max_results * 5, 100)
        api_hub = self.naver_api_provider == "api_hub"
        headers = (
            {
                "X-NCP-APIGW-API-KEY-ID": self.naver_client_id,
                "X-NCP-APIGW-API-KEY": self.naver_client_secret,
            }
            if api_hub
            else {
                "X-Naver-Client-Id": self.naver_client_id,
                "X-Naver-Client-Secret": self.naver_client_secret,
            }
        )
        items: list[MediaContent] = []
        total = 0
        next_start = start
        while next_start <= 1000 and len(items) < request.max_results:
            params = {
                "query": self._effective_query(request.query),
                # A date window must be scanned newest-first. Naver does not
                # expose server-side from/to parameters for News Search.
                "display": fetch_size,
                "start": next_start,
                "sort": "date" if request.published_after or request.published_before or request.order.value == "date" else "sim",
            }
            if api_hub:
                params["format"] = "json"
            response = self.client.get(
                self.naver_api_hub_url if api_hub else self.naver_api_url,
                params=params,
                headers=headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if response.status_code == 429 or response.status_code >= 500:
                    raise ConnectorTransientError(f"Naver News API {response.status_code}: {response.text}") from exc
                raise ConnectorError(f"Naver News API {response.status_code}: {response.text}") from exc
            payload = response.json()
            articles = payload.get("items", [])
            total = min(int(payload.get("total", 0)), 1000)
            oldest_published_at: datetime | None = None
            for article in articles:
                published_at = parsedate_to_datetime(article["pubDate"]).astimezone(timezone.utc)
                oldest_published_at = min(oldest_published_at, published_at) if oldest_published_at else published_at
                if not self._in_published_window(published_at, request):
                    continue
                title = self._plain_text(article.get("title"))
                description = self._plain_text(article.get("description"))
                if not self._matches_query(request.query, title, description):
                    continue
                article_url = article.get("originallink") or article.get("link")
                source = self._source_for_url(article_url, request.news_sources)
                if request.news_sources and source is None:
                    continue
                thumbnail_url = self._open_graph_thumbnail(article_url, source)
                raw = dict(article)
                raw["fanheat_link_policy"] = {
                    "publisher": source.name if source else (urlparse(article_url).hostname or "Naver News"),
                    "article_link_only": True,
                    "thumbnail_preview_allowed": bool(source and source.allow_thumbnail_preview),
                    "thumbnail_origin": "open_graph" if thumbnail_url else None,
                    "naver_result_url": article.get("link"),
                }
                items.append(MediaContent(
                    source=Source.NEWS,
                    source_content_id=hashlib.sha256(article_url.encode()).hexdigest(),
                    content_type=ContentType.ARTICLE,
                    author=Author(name=source.name if source else (urlparse(article_url).hostname or "Naver News")),
                    title=title,
                    text=description,
                    url=article_url,
                    thumbnail_url=thumbnail_url,
                    published_at=published_at,
                    raw=raw,
                ))
                if len(items) >= request.max_results:
                    break
            next_start += fetch_size
            if not articles or next_start > total:
                break
            if request.published_after and oldest_published_at and oldest_published_at < request.published_after:
                break
        next_cursor = str(next_start) if next_start <= total else None
        return ConnectorPage(items=items, next_cursor=next_cursor)

    @staticmethod
    def _in_published_window(published_at: datetime, request: CollectionRequest) -> bool:
        if request.published_after and published_at < request.published_after:
            return False
        if request.published_before and published_at >= request.published_before:
            return False
        return True

    @staticmethod
    def _plain_text(value: str | None) -> str | None:
        if not value:
            return None
        return re.sub(r"<[^>]+>", "", unescape(value)).strip() or None

    @classmethod
    def _search_tokens(cls, value: str | None) -> list[str]:
        normalized = (
            (value or "").casefold()
            .replace("k-pop", "kpop")
            .replace("k pop", "kpop")
            .replace("k팝", "kpop")
        )
        return re.findall(r"[0-9a-z가-힣]+", normalized)

    @classmethod
    def _effective_query(cls, query: str) -> str:
        stripped = query.strip()
        return cls._ambiguous_query_expansions.get(stripped.casefold(), stripped)

    @classmethod
    def _matches_query(cls, query: str, title: str | None, description: str | None) -> bool:
        """Reject Naver's semantic expansions that do not actually mention the query.

        Broad single terms such as `공항` additionally need an entertainment/K-pop
        marker so airport incidents and travel news cannot enter the media queue.
        """
        effective_query = cls._effective_query(query)
        query_tokens = list(dict.fromkeys(cls._search_tokens(effective_query)))
        haystack_tokens = cls._search_tokens(f"{title or ''} {description or ''}")
        compact_haystack = "".join(haystack_tokens)
        if query_tokens and not all(token in compact_haystack for token in query_tokens):
            return False
        compact_title = "".join(cls._search_tokens(title))
        if query_tokens and not any(token in compact_title for token in query_tokens):
            return False
        ambiguous_key = query.strip().casefold()
        if ambiguous_key in cls._ambiguous_query_expansions:
            if not any(anchor in compact_title for anchor in cls._ambiguous_title_anchors[ambiguous_key]):
                return False
        return True

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
        if request.published_before:
            params["to"] = request.published_before.isoformat()
        response = self.client.get(self.news_api_url, params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code == 429 or response.status_code >= 500:
                raise ConnectorTransientError(f"News API {response.status_code}: {response.text}") from exc
            raise ConnectorError(f"News API {response.status_code}: {response.text}") from exc
        payload = response.json()
        items = []
        for article in payload.get("articles", []):
            if not article.get("url"):
                continue
            source = self._source_for_url(article["url"], request.news_sources)
            if request.news_sources and source is None:
                continue
            item = self._normalize_article(article, source)
            if self._in_published_window(item.published_at, request):
                items.append(item)
        next_cursor = str(page + 1) if page * request.max_results < payload.get("totalResults", 0) else None
        return ConnectorPage(items=items, next_cursor=next_cursor)

    def _collect_configured_sources(self, request: CollectionRequest) -> ConnectorPage:
        feeds = [source.rss_url for source in request.news_sources if source.enabled and source.rss_url]
        items = self._collect_rss(request, feeds=feeds).items if feeds else []
        seen = {item.url for item in items}
        for source in request.news_sources:
            if not source.enabled or not source.source_url or len(items) >= request.max_results:
                continue
            for item in self._collect_open_graph_source(request, source):
                if item.url not in seen:
                    items.append(item)
                    seen.add(item.url)
                if len(items) >= request.max_results:
                    break
        return ConnectorPage(items=items[:request.max_results])

    def _collect_rss(self, request: CollectionRequest, feeds: list[str] | None = None) -> ConnectorPage:
        terms = request.query.casefold().split()
        items: list[MediaContent] = []
        configured_feeds = [source.rss_url for source in request.news_sources if source.enabled and source.rss_url]
        selected_feeds = feeds if feeds is not None else (configured_feeds or self.rss_feeds)
        for url in selected_feeds:
            response = self.client.get(
                url,
                headers={
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
                    "User-Agent": "Mozilla/5.0 (compatible; FANHEATBot/1.0; +https://fanheat.io)",
                },
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            source_name = feed.feed.get("title", url)
            for entry in feed.entries:
                if terms and not self._matches_query(
                    request.query, entry.get("title"), entry.get("summary")
                ):
                    continue
                source = self._source_for_url(entry.get("link"), request.news_sources)
                if request.news_sources and source is None:
                    continue
                item = self._normalize_feed_entry(entry, source_name, source)
                if self._in_published_window(item.published_at, request):
                    items.append(item)
                if len(items) >= request.max_results:
                    return ConnectorPage(items=items)
        return ConnectorPage(items=items)

    def _collect_open_graph_source(
        self, request: CollectionRequest, source: NewsSourceSetting
    ) -> list[MediaContent]:
        listing = self._fetch_public_html(source.source_url, source)
        if listing is None:
            return []
        listing_url, soup = listing
        terms = request.query.casefold().split()
        candidates: list[str] = []
        for link in soup.find_all("a", href=True):
            url = urljoin(listing_url, str(link.get("href") or "")).split("#", 1)[0]
            anchor_text = link.get_text(" ", strip=True).casefold()
            parsed = urlparse(url)
            if url == listing_url or self._source_for_url(url, [source]) is None:
                continue
            if parsed.path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf")):
                continue
            looks_like_article = any(part in parsed.path.casefold() for part in ("/news", "/article", "/view", "/story"))
            if terms and not all(term in anchor_text for term in terms) and not looks_like_article:
                continue
            if url not in candidates:
                candidates.append(url)
            if len(candidates) >= min(request.max_results * 5, 80):
                break

        items: list[MediaContent] = []
        for url in candidates:
            document = self._fetch_public_html(url, source)
            if document is None:
                continue
            final_url, article = document
            title = self._meta_content(article, "property", "og:title") or (
                article.title.get_text(" ", strip=True) if article.title else None
            )
            description = (
                self._meta_content(article, "property", "og:description")
                or self._meta_content(article, "name", "description")
            )
            if terms and not self._matches_query(request.query, title, description):
                continue
            published_at = self._open_graph_published_at(article)
            if (request.published_after or request.published_before) and (
                published_at is None or not self._in_published_window(published_at, request)
            ):
                continue
            thumbnail_url = None
            if source.allow_thumbnail_preview:
                raw_thumbnail = self._meta_content(article, "property", "og:image")
                if raw_thumbnail:
                    candidate = urljoin(final_url, raw_thumbnail)
                    if self._public_https_url(candidate):
                        thumbnail_url = candidate
            items.append(MediaContent(
                source=Source.NEWS,
                source_content_id=hashlib.sha256(final_url.encode()).hexdigest(),
                content_type=ContentType.ARTICLE,
                author=Author(name=source.name),
                title=self._plain_text(title),
                text=self._plain_text(description),
                url=final_url,
                thumbnail_url=thumbnail_url,
                published_at=published_at or datetime.now(timezone.utc),
                raw={"fanheat_link_policy": {
                    "publisher": source.name,
                    "article_link_only": True,
                    "thumbnail_preview_allowed": source.allow_thumbnail_preview,
                    "thumbnail_origin": "open_graph" if thumbnail_url else None,
                    "discovery_origin": "publisher_page",
                    "publisher_source_url": source.source_url,
                }},
            ))
            if len(items) >= request.max_results:
                break
        return items

    @staticmethod
    def _meta_content(soup: BeautifulSoup, attribute: str, value: str) -> str | None:
        tag = soup.find("meta", attrs={attribute: value})
        content = str(tag.get("content") or "").strip() if tag else ""
        return content or None

    @classmethod
    def _open_graph_published_at(cls, soup: BeautifulSoup) -> datetime | None:
        value = (
            cls._meta_content(soup, "property", "article:published_time")
            or cls._meta_content(soup, "name", "article:published_time")
            or cls._meta_content(soup, "name", "date")
        )
        if not value:
            return None
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
        except ValueError:
            try:
                return parsedate_to_datetime(value).astimezone(timezone.utc)
            except (TypeError, ValueError):
                return None

    @staticmethod
    def _source_for_url(url: str | None, sources: list[NewsSourceSetting]) -> NewsSourceSetting | None:
        if not url:
            return None
        hostname = (urlparse(url).hostname or "").casefold().removeprefix("www.")
        for source in sources:
            if source.enabled and any(hostname == domain or hostname.endswith(f".{domain}") for domain in source.domains):
                return source
        return None

    @staticmethod
    def _thumbnail_from_entry(entry: Any) -> str | None:
        candidates = list(entry.get("media_thumbnail", [])) + list(entry.get("media_content", []))
        candidates += list(entry.get("enclosures", []))
        for candidate in candidates:
            url = candidate.get("url") or candidate.get("href")
            media_type = str(candidate.get("type") or candidate.get("medium") or "").casefold()
            if url and (not media_type or media_type == "image" or media_type.startswith("image/")):
                return url
        return None

    @staticmethod
    def _public_https_url(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return False
        hostname = parsed.hostname.casefold()
        if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
            return False
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
        except OSError:
            return False
        try:
            return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)
        except ValueError:
            return False

    def _open_graph_thumbnail(self, article_url: str, source: NewsSourceSetting | None) -> str | None:
        if not source or not source.allow_thumbnail_preview:
            return None
        document = self._fetch_public_html(article_url, source)
        if document is None:
            return None
        final_url, soup = document
        content = self._meta_content(soup, "property", "og:image")
        if not content:
            for attribute, key in (("property", "og:image:url"), ("name", "twitter:image"),
                                   ("name", "twitter:image:src"), ("property", "twitter:image")):
                content = self._meta_content(soup, attribute, key)
                if content:
                    break
        candidate = urljoin(final_url, content) if content else ""
        return candidate if candidate and self._public_https_url(candidate) else None

    def _fetch_public_html(
        self, url: str | None, source: NewsSourceSetting
    ) -> tuple[str, BeautifulSoup] | None:
        if not url or not self._public_https_url(url) or self._source_for_url(url, [source]) is None:
            return None
        try:
            with self.client.stream(
                "GET",
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "FANHEAT-Link-Preview/1.0",
                },
            ) as response:
                response.raise_for_status()
                redirect_urls = [str(item.url) for item in response.history] + [str(response.url)]
                if any(not self._public_https_url(url) for url in redirect_urls):
                    return None
                if self._source_for_url(str(response.url), [source]) is None:
                    return None
                content_type = response.headers.get("content-type", "").casefold()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    return None
                declared_size = response.headers.get("content-length")
                if declared_size and int(declared_size) > self.open_graph_max_bytes:
                    return None
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > self.open_graph_max_bytes:
                        return None
            return str(response.url), BeautifulSoup(bytes(body), "html.parser")
        except (httpx.HTTPError, OSError, TypeError, ValueError):
            return None

    def _normalize_article(self, article: dict[str, Any], source: NewsSourceSetting | None = None) -> MediaContent:
        api_thumbnail = article.get("urlToImage") if source and source.allow_thumbnail_preview else None
        if api_thumbnail and not self._public_https_url(api_thumbnail):
            api_thumbnail = None
        thumbnail_url = api_thumbnail or self._open_graph_thumbnail(article["url"], source)
        raw = dict(article)
        raw["fanheat_link_policy"] = {
            "publisher": source.name if source else article.get("source", {}).get("name"),
            "article_link_only": True,
            "thumbnail_preview_allowed": bool(source and source.allow_thumbnail_preview),
            "thumbnail_origin": "news_api" if api_thumbnail else ("open_graph" if thumbnail_url else None),
        }
        return MediaContent(
            source=Source.NEWS,
            source_content_id=hashlib.sha256(article["url"].encode()).hexdigest(),
            content_type=ContentType.ARTICLE,
            author=Author(name=article.get("source", {}).get("name") or article.get("author") or "Unknown"),
            title=article.get("title"), text=article.get("description"), url=article["url"],
            thumbnail_url=thumbnail_url,
            published_at=datetime.fromisoformat(article["publishedAt"].replace("Z", "+00:00")), raw=raw,
        )

    def _normalize_feed_entry(self, entry: Any, source_name: str, source: NewsSourceSetting | None = None) -> MediaContent:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at = datetime.fromtimestamp(timegm(published), timezone.utc) if published else datetime.now(timezone.utc)
        url = entry.get("link")
        feed_thumbnail = self._thumbnail_from_entry(entry) if source and source.allow_thumbnail_preview else None
        if feed_thumbnail and not self._public_https_url(feed_thumbnail):
            feed_thumbnail = None
        thumbnail_url = feed_thumbnail or self._open_graph_thumbnail(url, source)
        raw = dict(entry)
        raw["fanheat_link_policy"] = {
            "publisher": source.name if source else source_name,
            "article_link_only": True,
            "thumbnail_preview_allowed": bool(source and source.allow_thumbnail_preview),
            "thumbnail_origin": "rss" if feed_thumbnail else ("open_graph" if thumbnail_url else None),
        }
        return MediaContent(
            source=Source.NEWS,
            source_content_id=entry.get("id") or hashlib.sha256(url.encode()).hexdigest(),
            content_type=ContentType.ARTICLE,
            author=Author(name=source_name), title=entry.get("title"), text=entry.get("summary"),
            url=url,
            thumbnail_url=thumbnail_url,
            published_at=published_at,
            raw=raw,
        )
