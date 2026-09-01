from datetime import datetime, timezone

from media_collector.language_policy import apply_language_policy
from media_collector.schemas import (
    Author,
    CollectionRequest,
    ContentType,
    LanguageFilterMode,
    MediaContent,
    Source,
)


def media(content_id: str, title: str, channel: str, description: str = "") -> MediaContent:
    return MediaContent(
        source=Source.YOUTUBE,
        source_content_id=content_id,
        content_type=ContentType.VIDEO,
        author=Author(name=channel),
        title=title,
        text=description,
        url=f"https://youtube.com/watch?v={content_id}",
        published_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def request(mode: LanguageFilterMode, max_results: int = 15) -> CollectionRequest:
    return CollectionRequest(
        source=Source.YOUTUBE,
        query="K-POP 컴백",
        max_results=max_results,
        region_code="KR",
        language_code="ko",
        language_filter_mode=mode,
    )


def test_strict_korean_keeps_only_korean_metadata_even_for_official_channels():
    korean = media("ko", "아이돌 신곡 컴백 무대", "한국 음악방송")
    foreign_fan = media("foreign", "Fans went insane during the concert", "World Pop Clips")
    official = media("official", "BTS Official Live Stage", "BANGTANTV")

    selected = apply_language_policy([foreign_fan, official, korean], request(LanguageFilterMode.STRICT))

    assert [item.source_content_id for item in selected] == ["ko"]


def test_prefer_korean_ranks_matching_content_before_foreign_results():
    foreign = media("foreign", "International concert highlights", "Global Music")
    korean = media("ko", "신곡 라이브 무대 공개", "음악중심")

    selected = apply_language_policy(
        [foreign, korean],
        request(LanguageFilterMode.PREFER, max_results=1),
    )

    assert [item.source_content_id for item in selected] == ["ko"]


def test_strict_korean_uses_description_when_title_is_english():
    described_in_korean = media(
        "description",
        "IVE COMEBACK STAGE",
        "Fan News Korea",
        "아이브의 새로운 컴백 무대와 신곡을 소개합니다.",
    )

    selected = apply_language_policy([described_in_korean], request(LanguageFilterMode.STRICT))

    assert [item.source_content_id for item in selected] == ["description"]
