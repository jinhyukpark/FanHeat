"""Discover indexed video links; never crawl TikTok search or download videos."""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from media_collector.schemas import Author, ContentType, MediaContent, Source
from .base import Connector, ConnectorConfigurationError, ConnectorError, ConnectorPage, ConnectorTransientError


class TikTokSearchConnector(Connector):
    def __init__(self, client_id, client_secret, provider="developers", timeout=20, client=None):
        self.client_id, self.client_secret, self.provider = client_id, client_secret, provider
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    @staticmethod
    def video_url(value):
        try:
            parsed = urlsplit(value)
            if (parsed.scheme != "https" or parsed.hostname not in {"www.tiktok.com", "tiktok.com"}
                    or parsed.username or parsed.password or parsed.port not in {None, 443}):
                return None
            match = re.fullmatch(r"/@([\w.-]+)/video/(\d{19})/?", parsed.path, flags=re.ASCII)
            return (f"https://www.tiktok.com/@{match[1]}/video/{match[2]}", match[1], match[2]) if match else None
        except (ValueError, TypeError):
            return None

    def collect(self, request, cursor=None):
        if not self.client_id or not self.client_secret:
            raise ConnectorConfigurationError("NAVER_CLIENT_ID/SECRET을 설정하세요.")
        hub = self.provider == "api_hub"
        headers = ({"X-NCP-APIGW-API-KEY-ID": self.client_id, "X-NCP-APIGW-API-KEY": self.client_secret}
                   if hub else {"X-Naver-Client-Id": self.client_id, "X-Naver-Client-Secret": self.client_secret})
        endpoint = ("https://naverapihub.apigw.ntruss.com/search/v1/webkr" if hub
                    else "https://openapi.naver.com/v1/search/webkr.json")
        response = self.client.get(endpoint, headers=headers, params={
            "query": f"site:tiktok.com {request.query}", "display": 100, "start": 1, "format": "json",
        })
        self._check(response, "네이버 웹검색")
        items, seen = [], set()
        for result in response.json().get("items", []):
            video = self.video_url(result.get("link", ""))
            if not video or video[2] in seen:
                continue
            url, handle, video_id = video
            seen.add(video_id)
            embed = self.client.get("https://www.tiktok.com/oembed", params={"url": url})
            if embed.status_code in {400, 404, 410}:
                continue
            self._check(embed, "TikTok 임베드 조회")
            data = embed.json()
            if data.get("type") != "video" or data.get("provider_name") != "TikTok":
                continue
            # oEmbed has no publication date: retain discovery time, explicitly labelled.
            items.append(MediaContent(
                source=Source.TIKTOK, source_content_id=video_id, content_type=ContentType.VIDEO,
                author=Author(name=data.get("author_name") or handle, handle=handle),
                title=data.get("title") or f"TikTok · @{handle}", text=data.get("title") or None,
                url=url, published_at=datetime.now(timezone.utc),
                raw={"discovery_provider": "naver_web", "query": request.query,
                     "timestamp_basis": "discovered_at", "playback_verified": False,
                     "oembed_verified": True, "title": data.get("title"), "url": url},
            ))
            if len(items) >= request.max_results:
                break
        return ConnectorPage(items=items, next_cursor=None)

    @staticmethod
    def _check(response, label):
        if response.status_code == 429 or response.status_code >= 500:
            raise ConnectorTransientError(f"{label} 일시 오류 ({response.status_code}). 잠시 후 다시 실행하세요.")
        if response.status_code != 200:
            raise ConnectorError(f"{label} 실패 ({response.status_code}). 검색 API 권한과 연결을 확인하세요.")
