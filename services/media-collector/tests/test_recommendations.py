from datetime import datetime, timedelta, timezone

import httpx

from media_collector.recommendations import (
    build_trending_idol_recommendations,
    fetch_naver_search_trends,
    score_naver_trend_results,
)


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
    artists = [{"id": 1, "name": "테스트돌", "name_ko": "테스트돌"}]

    result = build_trending_idol_recommendations(artists, [], artist_limit=1)

    assert result["artists"][0]["activity_keywords"] == ["컴백", "신곡"]
    assert result["queries"] == ["테스트돌", "테스트돌 컴백", "테스트돌 신곡"]


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
