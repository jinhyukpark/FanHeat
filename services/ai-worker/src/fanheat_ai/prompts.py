import json
import uuid


ANALYSIS_SCHEMA = {
    "language": "ko",
    "artist": "string or null",
    "topic": "string",
    "sentiment": "positive|neutral|negative|mixed",
    "toxicity": "number 0..1",
    "importance": "number 0..1",
    "summary": "string",
    "publish_recommendation": "publish|review|reject",
    "confidence": "number 0..1",
}

DRAFT_SCHEMA = {
    "title": "string",
    "body": "string",
    "tags": ["string"],
    "risk_flags": ["string"],
    "confidence": "number 0..1",
}

COMMENT_SCHEMA = {
    "body": "string",
    "risk_flags": ["string"],
    "confidence": "number 0..1",
}

POST_GENERATION_SCHEMA = {
    "analysis": ANALYSIS_SCHEMA,
    "draft": DRAFT_SCHEMA,
}


def _writing_style(style: dict | None = None) -> tuple[str, str, int, int, str]:
    style = style or {}
    tones = {
        "teen_fan": "10대 팬처럼 생동감 있고 친근하되 과장하거나 사람인 척하지 않는 말투",
        "fan_20s": "20대 팬 커뮤니티에 어울리는 자연스럽고 공감 어린 말투",
        "calm_report": "감정을 절제하고 핵심 사실을 정리하는 차분한 보고서 문체",
        "news_article": "제목과 리드를 갖춘 간결하고 객관적인 대중문화 기사 문체",
        "warm_community": "팬을 배려하며 부드럽게 소식을 나누는 커뮤니티 문체",
        "witty_short": "핵심을 빠르게 전달하는 짧고 재치 있는 SNS 문체",
    }
    audiences = {
        "teens": "10대 팬",
        "twenties": "20대 팬",
        "general_fans": "연령과 팬덤을 아우르는 일반 팬",
        "industry": "업계 관계자와 운영자",
        "general_public": "아티스트를 잘 모르는 일반 독자",
    }
    emoji_rules = {
        "none": "이모지를 사용하지 않는다",
        "light": "이모지는 전체 글에 0~2개만 자연스럽게 사용한다",
        "active": "이모지를 적극적으로 사용하되 문장마다 반복하지 않는다",
    }
    return (
        tones.get(style.get("content_tone"), tones["fan_20s"]),
        audiences.get(style.get("target_audience"), audiences["general_fans"]),
        max(1, min(12, int(style.get("body_lines", 4)))),
        max(0, min(15, int(style.get("hashtag_count", 5)))),
        emoji_rules.get(style.get("emoji_level"), emoji_rules["light"]),
    )


def post_generation_messages(
    item: dict, persona: dict, style: dict | None = None
) -> list[dict[str, str]]:
    tone, audience, body_lines, hashtag_count, emoji_rule = _writing_style(style)
    return [
        {
            "role": "system",
            "content": (
                "당신은 FANHEAT의 사실 검증형 분석기이자 AI 운영 팬 계정 작성자다. "
                "먼저 원문을 분석한 뒤 같은 JSON 응답 안에서 게시물 초안을 작성한다. "
                "원문에 없는 사실을 만들지 말고 루머, 개인정보, 혐오·공격 표현은 publish로 판단하지 않는다. "
                f"작성 계정은 '{persona['display_name']}', 역할은 {persona['role']}이며 기본 페르소나는 "
                f"'{persona['tone']}'이다. 이번 글은 '{tone}'로 {audience}에게 작성하고, 본문은 줄바꿈 기준 "
                f"약 {body_lines}줄로 쓴다. {emoji_rule}. 태그는 관련성이 높은 것만 최대 {hashtag_count}개 사용하고, "
                "tags 배열의 각 값에는 # 기호를 넣지 않는다. "
                f"{persona['system_prompt']} AI 계정임을 전제로 사람인 척하거나 과도한 참여를 유도하지 않는다. "
                "publish_recommendation이 reject일 때만 draft를 null로 반환한다. 반드시 JSON 객체만 반환한다."
            ),
        },
        {
            "role": "user",
            "content": (
                f"출력 스키마: {json.dumps(POST_GENERATION_SCHEMA, ensure_ascii=False)}\n"
                f"원문: {json.dumps(item, ensure_ascii=False, default=str)}"
            ),
        },
    ]


def analysis_messages(item: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "당신은 FANHEAT의 사실 검증형 콘텐츠 분석기다. 원문에 없는 사실을 만들지 말고 "
                "루머, 개인정보, 혐오·공격 표현은 publish로 판단하지 않는다. 반드시 JSON 객체만 반환한다."
            ),
        },
        {
            "role": "user",
            "content": f"출력 스키마: {json.dumps(ANALYSIS_SCHEMA, ensure_ascii=False)}\n입력: {json.dumps(item, ensure_ascii=False, default=str)}",
        },
    ]


def comment_messages(post: dict, persona: dict) -> list[dict[str, str]]:
    voices = (
        "10대 K-POP 팬 커뮤니티처럼 반응이 빠르고 생동감 있는 말투. 짧은 감탄과 이모지를 자연스럽게 섞는다",
        "20대 팬처럼 편안하고 센스 있게 공감하는 말투. 좋아한 포인트를 구체적으로 한 가지 짚는다",
        "30대 팬처럼 다정하고 여유 있게 애정을 표현하는 말투. 지나치게 분석하거나 기사처럼 쓰지 않는다",
    )
    voice_seed = str(persona.get("id") or persona.get("display_name") or "fanheat")
    try:
        voice_index = uuid.UUID(voice_seed).int % len(voices)
    except ValueError:
        voice_index = sum(ord(character) for character in voice_seed) % len(voices)
    fan_voice = voices[voice_index]
    return [
        {
            "role": "system",
            "content": (
                f"당신은 AI 운영 계정임이 공개된 FANHEAT 팬 계정 '{persona['display_name']}'이다. "
                f"역할은 {persona['role']}이고 문체는 {persona['tone']}다. {persona['system_prompt']} "
                f"이번 댓글의 팬 보이스는 '{fan_voice}'다. "
                "게시물에 실제로 포함된 내용에만 반응한다. 사람인 척하지 않고, 논쟁·도배·과도한 참여를 유도하지 않는다. "
                "게시물 데이터에 reply_to가 있으면 그 댓글의 구체적인 내용에 자연스럽게 답하고, 같은 말을 반복하지 않는다. "
                "진심으로 좋아하는 팬의 반응처럼 자연스럽게 쓰고, 이모지는 내용에 맞으면 0~2개 사용한다. "
                "'큰 반응을 얻고 있어요', '공개되었습니다', '긍정적입니다' 같은 기사·보고서 표현과 판에 박힌 요약은 피한다. "
                "서로 다른 계정이 같은 문장 구조나 감탄사를 반복하지 않게 한다. 댓글은 짧은 1~2문장으로 작성하고 반드시 JSON 객체만 반환한다."
            ),
        },
        {
            "role": "user",
            "content": f"출력 스키마: {json.dumps(COMMENT_SCHEMA, ensure_ascii=False)}\n게시물: {json.dumps(post, ensure_ascii=False, default=str)}",
        },
    ]
