import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from media_collector.schemas import Author, CollectionRequest, ContentType, MediaContent, Metrics, Source

from .base import Connector, ConnectorConfigurationError, ConnectorError, ConnectorPage, ConnectorTransientError


class TikTokConnector(Connector):
    """Collect public video metadata through TikTok's approved Research API."""

    url = "https://open.tiktokapis.com/v2/research/video/query/"
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    fields = (
        "id,video_description,create_time,region_code,share_count,view_count,"
        "like_count,comment_count,hashtag_names,username,video_duration"
    )

    def __init__(
        self,
        access_token: str | None,
        timeout: float = 20,
        client: httpx.Client | None = None,
        *,
        client_key: str | None = None,
        client_secret: str | None = None,
    ):
        self.access_token = access_token
        self.client_key = client_key
        self.client_secret = client_secret
        self._generated_access_token: str | None = None
        self._token_expires_at = 0.0
        self.client = client or httpx.Client(timeout=timeout)

    def _authorization_token(self) -> str:
        if self.access_token:
            return self.access_token
        if self._generated_access_token and time.monotonic() < self._token_expires_at:
            return self._generated_access_token
        if not self.client_key or not self.client_secret:
            raise ConnectorConfigurationError(
                "TIKTOK_CLIENT_KEY/SECRET or TIKTOK_RESEARCH_ACCESS_TOKEN is not configured"
            )
        response = self.client.post(
            self.token_url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"TikTok token API {response.status_code}: {response.text}") from exc
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise ConnectorError("TikTok token API response did not include access_token")
        self._generated_access_token = str(token)
        self._token_expires_at = time.monotonic() + max(60, int(payload.get("expires_in") or 7200) - 300)
        return self._generated_access_token

    def collect(self, request: CollectionRequest, cursor: str | None = None) -> ConnectorPage:
        access_token = self._authorization_token()

        now = datetime.now(timezone.utc)
        end = min(request.published_before or now, now)
        start = request.published_after or (end - timedelta(days=1))
        if end - start > timedelta(days=30):
            raise ConnectorError("TikTok Research API 수집 기간은 최대 30일입니다")

        conditions: list[dict[str, Any]] = [{
            "operation": "EQ",
            "field_name": "keyword",
            "field_values": [request.query.strip()],
        }]
        if request.region_code:
            conditions.insert(0, {
                "operation": "IN",
                "field_name": "region_code",
                "field_values": [request.region_code],
            })
        body: dict[str, Any] = {
            "query": {"and": conditions},
            "max_count": min(request.max_results, 100),
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
            "is_random": False,
        }
        if cursor:
            try:
                cursor_data = json.loads(cursor)
                body["cursor"] = int(cursor_data["cursor"])
                body["search_id"] = str(cursor_data["search_id"])
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                raise ConnectorError("TikTok pagination cursor is invalid") from exc

        response = self.client.post(
            self.url,
            params={"fields": self.fields},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=body,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code == 429 or response.status_code >= 500:
                raise ConnectorTransientError(f"TikTok API {response.status_code}: {response.text}") from exc
            raise ConnectorError(f"TikTok API {response.status_code}: {response.text}") from exc

        payload = response.json()
        error = payload.get("error") or {}
        if error.get("code") not in {None, "", "ok"}:
            raise ConnectorError(f"TikTok API {error.get('code')}: {error.get('message', '')}")
        data = payload.get("data") or {}
        videos = data.get("videos") or []
        next_cursor = None
        if data.get("has_more") and data.get("search_id") is not None and data.get("cursor") is not None:
            next_cursor = json.dumps({"cursor": data["cursor"], "search_id": data["search_id"]})
        return ConnectorPage(
            items=[self._normalize(video) for video in videos],
            next_cursor=next_cursor,
        )

    @staticmethod
    def _normalize(video: dict[str, Any]) -> MediaContent:
        video_id = str(video.get("id") or video.get("video_id"))
        username = str(video.get("username") or "").lstrip("@")
        description = str(video.get("video_description") or "").strip()
        hashtags = [str(value) for value in video.get("hashtag_names") or [] if value]
        return MediaContent(
            source=Source.TIKTOK,
            source_content_id=video_id,
            content_type=ContentType.VIDEO,
            author=Author(name=username or "TikTok creator", handle=username or None),
            title=description[:200] or f"TikTok video {video_id}",
            text=description or None,
            url=f"https://www.tiktok.com/@{username or 'tiktok'}/video/{video_id}",
            published_at=datetime.fromtimestamp(int(video["create_time"]), tz=timezone.utc),
            metrics=Metrics(
                views=video.get("view_count"),
                likes=video.get("like_count"),
                comments=video.get("comment_count"),
                shares=video.get("share_count"),
            ),
            entities=hashtags,
            raw=video,
        )
