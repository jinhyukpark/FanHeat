from datetime import datetime
from typing import Any

import httpx

from media_collector.schemas import Author, CollectionRequest, ContentType, MediaContent, Metrics, Source

from .base import Connector, ConnectorConfigurationError, ConnectorError, ConnectorPage, ConnectorTransientError


class YouTubeConnector(Connector):
    base_url = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str | None, timeout: float = 20, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=timeout)

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise ConnectorConfigurationError("YOUTUBE_API_KEY is not configured")
        response = self.client.get(f"{self.base_url}/{endpoint}", params={**params, "key": self.api_key})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.json().get("error", {}).get("message", response.text)
            if response.status_code == 429 or response.status_code >= 500:
                raise ConnectorTransientError(f"YouTube API {response.status_code}: {detail}") from exc
            raise ConnectorError(f"YouTube API {response.status_code}: {detail}") from exc
        return response.json()

    def collect(self, request: CollectionRequest, cursor: str | None = None) -> ConnectorPage:
        candidate_limit = min(max(request.max_results * 4, request.max_results), 50)
        params: dict[str, Any] = {
            "part": "snippet",
            "type": "video",
            # Search filtering saves quota and avoids obvious non-embeddable
            # results, while the videos.list status check below remains the
            # source of truth before an item is persisted.
            "videoEmbeddable": "true",
            "q": request.query,
            "maxResults": candidate_limit,
            "order": request.order.value,
        }
        if cursor:
            params["pageToken"] = cursor
        if request.published_after:
            params["publishedAfter"] = request.published_after.isoformat().replace("+00:00", "Z")
        if request.region_code:
            params["regionCode"] = request.region_code
        if request.language_code:
            params["relevanceLanguage"] = request.language_code

        search = self._get("search", params)
        snippets = {item["id"]["videoId"]: item["snippet"] for item in search.get("items", [])}
        if not snippets:
            return ConnectorPage(next_cursor=search.get("nextPageToken"))

        videos = self._get(
            "videos",
            {"part": "snippet,statistics,status", "id": ",".join(snippets), "maxResults": len(snippets)},
        )
        items = [
            self._normalize(item)
            for item in videos.get("items", [])
            if self._is_publicly_embeddable(item)
        ]
        return ConnectorPage(items=items, next_cursor=search.get("nextPageToken"))

    @staticmethod
    def _is_publicly_embeddable(item: dict[str, Any]) -> bool:
        status = item.get("status") or {}
        return status.get("privacyStatus") == "public" and status.get("embeddable") is True

    @staticmethod
    def _normalize(item: dict[str, Any]) -> MediaContent:
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        thumbnails = snippet.get("thumbnails", {})
        thumbnail = thumbnails.get("maxres") or thumbnails.get("high") or thumbnails.get("default") or {}
        return MediaContent(
            source=Source.YOUTUBE,
            source_content_id=item["id"],
            content_type=ContentType.VIDEO,
            author=Author(source_id=snippet.get("channelId"), name=snippet.get("channelTitle", "Unknown")),
            title=snippet.get("title"),
            text=snippet.get("description"),
            url=f"https://www.youtube.com/watch?v={item['id']}",
            thumbnail_url=thumbnail.get("url"),
            published_at=datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00")),
            metrics=Metrics(
                views=int(stats["viewCount"]) if "viewCount" in stats else None,
                likes=int(stats["likeCount"]) if "likeCount" in stats else None,
                comments=int(stats["commentCount"]) if "commentCount" in stats else None,
            ),
            raw=item,
        )
