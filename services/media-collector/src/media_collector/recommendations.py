import math
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import get_settings


ACTIVITY_KEYWORDS = (
    "컴백",
    "신곡",
    "앨범",
    "콘서트",
    "팬미팅",
    "쇼케이스",
    "뮤직비디오",
    "직캠",
    "인터뷰",
    "공항패션",
    "음원 차트",
    "월드투어",
    "데뷔",
    "수상",
)
FALLBACK_ACTIVITY_KEYWORDS = ("컴백", "신곡")
NAVER_TREND_CACHE_SECONDS = 6 * 60 * 60
NAVER_TREND_REFERENCE = {"groupName": "KPOP 기준", "keywords": ["KPOP", "케이팝", "아이돌"]}
_naver_trend_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def _search_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).casefold().strip()


def _average_ratio(data: list[dict[str, Any]], start: int, end: int | None = None) -> float:
    values = [float(item.get("ratio") or 0) for item in data[start:end]]
    return sum(values) / len(values) if values else 0.0


def score_naver_trend_results(results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Convert NAVER's per-request ratios into scores comparable across batches."""
    by_title = {str(result.get("title") or ""): result.get("data") or [] for result in results}
    reference = by_title.get(NAVER_TREND_REFERENCE["groupName"], [])
    reference_recent = _average_ratio(reference, -7)
    reference_previous = _average_ratio(reference, -14, -7)
    reference_momentum = reference_recent / reference_previous if reference_previous else 1.0
    scores: dict[str, dict[str, float]] = {}
    for title, data in by_title.items():
        if title == NAVER_TREND_REFERENCE["groupName"]:
            continue
        recent = _average_ratio(data, -7)
        previous = _average_ratio(data, -14, -7)
        relative_volume = recent / reference_recent * 100 if reference_recent else 0.0
        raw_momentum = recent / previous if previous else (1.0 if recent else 0.0)
        momentum = raw_momentum / reference_momentum if reference_momentum else raw_momentum
        momentum_factor = 0.65 + min(2.0, max(0.5, momentum)) * 0.35
        scores[title] = {
            "score": round(relative_volume * momentum_factor, 2),
            "relative_volume": round(relative_volume, 2),
            "momentum": round(momentum, 3),
        }
    return scores


def fetch_naver_search_trends(
    artists: list[dict[str, Any]],
    *,
    client_id: str | None,
    client_secret: str | None,
    provider: str,
    client: httpx.Client | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    if not client_id or not client_secret:
        return {"status": "not_configured", "scores": {}}
    korean_now = end_date or datetime.now(ZoneInfo("Asia/Seoul"))
    end = korean_now.date()
    start = end - timedelta(days=29)
    cache_key = (provider, end.isoformat(), tuple(str(artist["name"]) for artist in artists))
    cached = _naver_trend_cache.get(cache_key)
    if client is None and cached and time.monotonic() - cached[0] < NAVER_TREND_CACHE_SECONDS:
        return cached[1] | {"cached": True}

    api_hub = provider == "api_hub"
    url = (
        "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
        if api_hub
        else "https://openapi.naver.com/v1/datalab/search"
    )
    headers = (
        {"X-NCP-APIGW-API-KEY-ID": client_id, "X-NCP-APIGW-API-KEY": client_secret}
        if api_hub
        else {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    )
    http = client or httpx.Client(timeout=20)
    scores: dict[str, dict[str, float]] = {}
    try:
        for offset in range(0, len(artists), 4):
            batch = artists[offset : offset + 4]
            keyword_groups = [NAVER_TREND_REFERENCE]
            keyword_groups.extend(
                {"groupName": artist["name"], "keywords": list(dict.fromkeys(artist.get("aliases") or [artist["name"]]))[:20]}
                for artist in batch
            )
            response = http.post(
                url,
                headers=headers | {"Content-Type": "application/json"},
                json={
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "timeUnit": "date",
                    "keywordGroups": keyword_groups,
                },
            )
            response.raise_for_status()
            scores.update(score_naver_trend_results(response.json().get("results") or []))
        result = {
            "status": "ok",
            "scores": scores,
            "provider": provider,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "cached": False,
        }
        if client is None:
            _naver_trend_cache[cache_key] = (time.monotonic(), result)
        return result
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        return {"status": "error", "scores": {}, "provider": provider, "status_code": status_code}
    finally:
        if client is None:
            http.close()


def build_trending_idol_recommendations(
    artists: Iterable[dict[str, Any]],
    media_items: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    artist_limit: int = 8,
) -> dict[str, Any]:
    """Rank public FANHEAT artists using recent mentions and on-site interest."""
    current = now or datetime.now(timezone.utc)
    media = list(media_items)
    ranked: list[dict[str, Any]] = []

    for artist in artists:
        name = str(artist.get("name_ko") or artist.get("name") or "").strip()
        raw_aliases = [name, artist.get("name")]
        slug = str(artist.get("slug") or "").replace("-", " ").strip()
        if len(slug) >= 3 and re.search(r"[a-zA-Z]", slug):
            raw_aliases.append(slug)
        aliases = {_search_text(alias) for alias in raw_aliases} - {""}
        if not name or not aliases:
            continue

        recent_mentions = 0
        mention_score = 0.0
        keyword_counts = {keyword: 0 for keyword in ACTIVITY_KEYWORDS}
        for item in media:
            content = _search_text(f"{item.get('title') or ''} {item.get('text') or ''}")
            if not content or not any(alias in content for alias in aliases):
                continue
            recent_mentions += 1
            published_at = item.get("published_at")
            if isinstance(published_at, datetime):
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
                age_days = max(0, (current - published_at).days)
            else:
                age_days = 30
            freshness = 6 if age_days <= 2 else 4 if age_days <= 7 else 2 if age_days <= 14 else 1
            source_weight = 1.5 if item.get("source") == "news" else 1.0
            mention_score += freshness * source_weight
            for keyword in ACTIVITY_KEYWORDS:
                if _search_text(keyword) in content:
                    keyword_counts[keyword] += 1

        visitor_today = max(0, int(artist.get("visitor_today") or 0))
        follower_count = max(0, int(artist.get("follower_count") or 0))
        visitor_total = max(0, int(artist.get("visitor_total") or 0))
        popularity_score = math.log1p(visitor_today) * 3 + math.log1p(follower_count) + math.log1p(visitor_total) * 0.25
        score = round(mention_score * 10 + popularity_score, 2)
        activity = [
            keyword
            for keyword, count in sorted(keyword_counts.items(), key=lambda pair: (-pair[1], ACTIVITY_KEYWORDS.index(pair[0])))
            if count
        ][:2]
        if len(activity) < 2:
            activity.extend(keyword for keyword in FALLBACK_ACTIVITY_KEYWORDS if keyword not in activity)
        ranked.append(
            {
                "id": artist.get("id"),
                "name": name,
                "aliases": list(dict.fromkeys(str(alias).strip() for alias in raw_aliases if str(alias or "").strip())),
                "score": score,
                "recent_mentions": recent_mentions,
                "activity_keywords": activity[:2],
                "visitor_today": visitor_today,
                "follower_count": follower_count,
            }
        )

    ranked.sort(
        key=lambda item: (
            item["recent_mentions"] > 0,
            item["score"],
            item["visitor_today"],
            item["follower_count"],
            item["name"],
        ),
        reverse=True,
    )
    selected = ranked[:artist_limit]
    queries: list[str] = []
    for artist in selected:
        candidates = [artist["name"], *(f"{artist['name']} {keyword}" for keyword in artist["activity_keywords"])]
        for candidate in candidates:
            if candidate not in queries:
                queries.append(candidate)
    return {"artists": selected, "queries": queries}


def trending_idol_recommendations(db: Session, *, artist_limit: int = 8, recent_days: int = 30) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=recent_days)
    artists = db.execute(
        text(
            """
            select id, slug, name, name_ko, role_description,
                   coalesce(follower_count, 0) follower_count,
                   coalesce(visitor_today, 0) visitor_today,
                   coalesce(visitor_total, 0) visitor_total
              from public.artists
             where active is true
               and coalesce(review_pending, false) is false
             order by updated_at desc nulls last
             limit 100
            """
        )
    ).mappings().all()
    media_items = db.execute(
        text(
            """
            select source, title, text, published_at
              from public.media_items
             where published_at >= :since
             order by published_at desc
             limit 2000
            """
        ),
        {"since": since},
    ).mappings().all()
    candidate_result = build_trending_idol_recommendations(artists, media_items, artist_limit=40)
    settings = get_settings()
    trend_candidates = [
        {"name": artist["name"], "aliases": artist["aliases"]} for artist in candidate_result["artists"]
    ]
    naver = fetch_naver_search_trends(
        trend_candidates,
        client_id=settings.naver_client_id,
        client_secret=settings.naver_client_secret,
        provider=settings.naver_api_provider,
    )
    trend_scores = naver["scores"]
    for artist in candidate_result["artists"]:
        trend = trend_scores.get(artist["name"], {})
        artist["naver_trend_score"] = trend.get("score")
        artist["naver_relative_volume"] = trend.get("relative_volume")
        artist["naver_momentum"] = trend.get("momentum")
    if trend_scores:
        candidate_result["artists"].sort(
            key=lambda artist: (artist["naver_trend_score"] or 0, artist["recent_mentions"], artist["score"]),
            reverse=True,
        )
    selected = candidate_result["artists"][:artist_limit]
    queries: list[str] = []
    for artist in selected:
        candidates = [artist["name"], *(f"{artist['name']} {keyword}" for keyword in artist["activity_keywords"])]
        for candidate in candidates:
            if candidate not in queries:
                queries.append(candidate)
    return {
        "artists": selected,
        "queries": queries,
        "lookback_days": recent_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "naver_trend": {key: value for key, value in naver.items() if key != "scores"},
    }
