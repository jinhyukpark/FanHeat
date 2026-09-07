from datetime import datetime, timedelta, timezone

import httpx
import media_collector.recommendations as recommendations

from media_collector.recommendations import (
    build_trending_idol_recommendations,
    discover_naver_kpop_candidates,
    extract_artist_candidates_from_news,
    fetch_naver_search_trends,
    score_naver_trend_results,
)


def test_artist_candidates_are_discovered_from_news_headline_subjects() -> None:
    result = extract_artist_candidates_from_news([
        "'5세대 아이돌 돌풍 주역' 리센느, 시상식 2관왕",
        "뜨겁다! 82메이저, 'HEAT' 컴백 첫 주 성료",
        "그룹 튜넥스, 미니 2집으로 글로벌 성장세 입증",
    ])

    assert [artist["name"] for artist in result] == ["82메이저", "리센느", "튜넥스"]
    assert result[0]["discovered_from"] == "naver_news"


def test_naver_news_discovery_queries_recent_kpop_topics() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": [{"title": "플레이브, 신곡 공개"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = discover_naver_kpop_candidates(
        client_id="client-id", client_secret="client-secret", provider="api_hub", client=client
    )

    assert result["status"] == "ok"
    assert result["artists"][0]["name"] == "플레이브"
    assert len(requests) == 3
    assert all(request.url.path == "/search/v1/news" for request in requests)


def test_recent_mentions_outweigh_static_popularity_and_extract_activity_keywords() -> None:
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    artists = [
        {"id": 1, "name": "인기선배", "name_ko": "인기선배", "visitor_today": 900, "follower_count": 1_000_000},
        {"id": 2, "name": "신인그룹", "name_ko": "신인그룹", "visitor_today": 10, "follower_count": 100},
    ]
    media = [
        {
            "source": "news",
            "title": "신인그룹 컴백, 새 앨범 쇼케이스 개최",
            "text": "신곡 무대를 공개했다.",
            "published_at": now - timedelta(hours=3),
        },
        {
            "source": "youtube",
            "title": "신인그룹 신곡 뮤직비디오",
            "text": "",
            "published_at": now - timedelta(days=1),
        },
    ]

    result = build_trending_idol_recommendations(artists, media, now=now, artist_limit=2)

    assert result["artists"][0]["name"] == "신인그룹"
    assert result["artists"][0]["recent_mentions"] == 2
    assert result["artists"][0]["activity_keywords"] == ["신곡", "컴백"]
    assert result["queries"][:3] == ["신인그룹", "신인그룹 신곡", "신인그룹 컴백"]


def test_recommendations_fall_back_to_comeback_and_new_song_terms() -> None:
    artists = [{"id": 1, "slug": "test-idol", "name": "테스트돌", "name_ko": "테스트돌"}]

    result = build_trending_idol_recommendations(artists, [], artist_limit=1)

    assert result["artists"][0]["activity_keywords"] == ["컴백", "신곡"]
    assert result["artists"][0]["slug"] == "test-idol"
    assert result["queries"] == ["테스트돌", "테스트돌 컴백", "테스트돌 신곡"]


def test_naver_news_discovery_is_merged_with_existing_artist_candidates(monkeypatch) -> None:
    class Result:
        def mappings(self):
            return self

        def all(self):
            return []

    class Database:
        def execute(self, *_args, **_kwargs):
            return Result()

    monkeypatch.setattr(
        recommendations,
        "build_trending_idol_recommendations",
        lambda *_args, **_kwargs: {
            "artists": [{"id": 1, "slug": "known", "name": "등록돌", "aliases": ["등록돌"], "score": 2,
                         "recent_mentions": 1, "activity_keywords": ["컴백"], "discovered_from": "fanheat"}],
            "queries": [],
        },
    )
    monkeypatch.setattr(
        recommendations,
        "discover_naver_kpop_candidates",
        lambda **_kwargs: {
            "status": "ok", "article_count": 3,
            "artists": [{"id": None, "name": "신규돌", "aliases": ["신규돌"], "score": 3,
                         "recent_mentions": 3, "activity_keywords": ["신곡"], "discovered_from": "naver_news"}],
        },
    )
    refresh_values = []

    def fake_trends(artists, **kwargs):
        refresh_values.append(kwargs["force_refresh"])
        return {"status": "ok", "scores": {artist["name"]: {"score": 10} for artist in artists}}

    monkeypatch.setattr(recommendations, "fetch_naver_search_trends", fake_trends)
    monkeypatch.setattr(
        recommendations,
        "get_settings",
        lambda: type("Settings", (), {"naver_client_id": "id", "naver_client_secret": "secret",
                                      "naver_api_provider": "developers"})(),
    )

    result = recommendations.trending_idol_recommendations(Database(), artist_limit=8, force_refresh=True)

    assert {artist["name"] for artist in result["artists"]} == {"등록돌", "신규돌"}
    assert next(artist for artist in result["artists"] if artist["name"] == "신규돌")["discovered_from"] == "naver_news"
    assert refresh_values == [True]


def test_recommendations_limit_the_number_of_artists() -> None:
    artists = [{"id": index, "name": f"그룹{index}", "visitor_today": index} for index in range(12)]

    result = build_trending_idol_recommendations(artists, [], artist_limit=8)

    assert len(result["artists"]) == 8
    assert len(result["queries"]) == 24


def test_naver_scores_are_normalized_against_shared_kpop_reference() -> None:
    results = [
        {"title": "KPOP 기준", "data": [{"ratio": 10}] * 14},
        {"title": "상승돌", "data": [{"ratio": 10}] * 7 + [{"ratio": 20}] * 7},
        {"title": "보합돌", "data": [{"ratio": 10}] * 14},
    ]

    scores = score_naver_trend_results(results)

    assert scores["상승돌"]["relative_volume"] == 200
    assert scores["상승돌"]["momentum"] == 2
    assert scores["상승돌"]["score"] > scores["보합돌"]["score"]


def test_naver_api_hub_batches_four_artists_with_reference_and_uses_cloud_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": group["groupName"], "data": [{"ratio": index + 1}] * 14}
                    for index, group in enumerate(body["keywordGroups"])
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    artists = [{"name": f"그룹{index}", "aliases": [f"그룹{index}"]} for index in range(5)]

    result = fetch_naver_search_trends(
        artists,
        client_id="client-id",
        client_secret="client-secret",
        provider="api_hub",
        client=client,
        end_date=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert result["status"] == "ok"
    assert len(requests) == 2
    assert all(request.url.path == "/search-trend/v1/search" for request in requests)
    assert requests[0].headers["x-ncp-apigw-api-key-id"] == "client-id"
    assert requests[0].headers["x-ncp-apigw-api-key"] == "client-secret"


def test_force_refresh_bypasses_a_cached_naver_result(monkeypatch) -> None:
    end_date = datetime(2026, 9, 7, tzinfo=timezone.utc)
    artists = [{"name": "새로운돌", "aliases": ["새로운돌"]}]
    cache_key = ("api_hub", end_date.date().isoformat(), ("새로운돌",))
    recommendations._naver_trend_cache[cache_key] = (
        recommendations.time.monotonic(),
        {"status": "ok", "scores": {"새로운돌": {"score": 1}}, "cached": False},
    )
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    real_client = httpx.Client
    monkeypatch.setattr(recommendations.httpx, "Client", lambda **_: real_client(transport=httpx.MockTransport(handler)))
    result = fetch_naver_search_trends(
        artists,
        client_id="client-id",
        client_secret="client-secret",
        provider="api_hub",
        end_date=end_date,
        force_refresh=True,
    )

    assert result["cached"] is False
    assert len(requests) == 1
    recommendations._naver_trend_cache.pop(cache_key, None)
