from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from media_collector.schemas import Author, CollectionOrder, CollectionRequest, ContentType, LanguageFilterMode, MediaContent, Metrics, Source

from .base import Connector, ConnectorConfigurationError, ConnectorError, ConnectorPage, ConnectorTransientError


class XConnector(Connector):
    url = "https://api.x.com/2/tweets/search/recent"

    def __init__(self, bearer_token: str | None, timeout: float = 20, client: httpx.Client | None = None):
        self.bearer_token = bearer_token
        self.client = client or httpx.Client(timeout=timeout)

    def collect(self, request: CollectionRequest, cursor: str | None = None) -> ConnectorPage:
        if not self.bearer_token:
            raise ConnectorConfigurationError("X_BEARER_TOKEN is not configured")
        query = request.query.strip()
        language = (request.language_code or "").split("-", 1)[0].lower()
        if request.language_filter_mode == LanguageFilterMode.STRICT and language and "lang:" not in query.lower():
            query = f"({query}) lang:{language}"
        if "-is:retweet" not in query.lower():
            query = f"{query} -is:retweet"
        params: dict[str, Any] = {
            "query": query,
            "max_results": max(10, min(request.max_results, 100)),
            "tweet.fields": "author_id,created_at,lang,public_metrics,entities",
            "expansions": "author_id,attachments.media_keys",
            "user.fields": "name,username",
            "media.fields": "media_key,type,url,preview_image_url",
            "sort_order": "recency" if request.order == CollectionOrder.DATE else "relevancy",
        }
        if cursor:
            params["next_token"] = cursor
        if request.published_after:
            # The recent-search endpoint accepts only the last seven days.
            earliest = datetime.now(timezone.utc) - timedelta(days=7) + timedelta(minutes=1)
            start_time = max(request.published_after.astimezone(timezone.utc), earliest)
            params["start_time"] = start_time.isoformat().replace("+00:00", "Z")
        response = self.client.get(self.url, params=params, headers={"Authorization": f"Bearer {self.bearer_token}"})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code == 429 or response.status_code >= 500:
                raise ConnectorTransientError(f"X API {response.status_code}: {response.text}") from exc
            raise ConnectorError(f"X API {response.status_code}: {response.text}") from exc
        payload = response.json()
        users = {user["id"]: user for user in payload.get("includes", {}).get("users", [])}
        media = {item["media_key"]: item for item in payload.get("includes", {}).get("media", [])}
        items = [self._normalize(tweet, users.get(tweet.get("author_id"), {}), media) for tweet in payload.get("data", [])]
        return ConnectorPage(
            items=items,
            next_cursor=payload.get("meta", {}).get("next_token"),
            rate_limit_remaining=_as_int(response.headers.get("x-rate-limit-remaining")),
            rate_limit_reset=response.headers.get("x-rate-limit-reset"),
        )

    @staticmethod
    def _normalize(tweet: dict[str, Any], user: dict[str, Any], media: dict[str, dict[str, Any]] | None = None) -> MediaContent:
        metrics = tweet.get("public_metrics", {})
        username = user.get("username")
        media = media or {}
        attached = [media[key] for key in tweet.get("attachments", {}).get("media_keys", []) if key in media]
        first_media = attached[0] if attached else {}
        thumbnail_url = first_media.get("preview_image_url") or (first_media.get("url") if first_media.get("type") == "photo" else None)
        return MediaContent(
            source=Source.X,
            source_content_id=tweet["id"],
            content_type=ContentType.POST,
            author=Author(source_id=tweet.get("author_id"), name=user.get("name", username or "Unknown"), handle=username),
            text=tweet["text"],
            url=f"https://x.com/{username or 'i'}/status/{tweet['id']}",
            thumbnail_url=thumbnail_url,
            published_at=datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00")),
            metrics=Metrics(
                likes=metrics.get("like_count"),
                comments=metrics.get("reply_count"),
                shares=metrics.get("retweet_count"),
            ),
            raw=tweet,
        )


def _as_int(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None
