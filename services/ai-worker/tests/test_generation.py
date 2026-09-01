import pytest
from pydantic import ValidationError

from fanheat_ai.prompts import post_generation_messages
from fanheat_ai.schemas import PostGenerationContent
from fanheat_ai.workload import LLMWorkCoordinator


ANALYSIS = {
    "language": "ko",
    "artist": "IU",
    "topic": "release",
    "sentiment": "positive",
    "toxicity": 0,
    "importance": 0.8,
    "summary": "새 영상이 공개됐다.",
    "publish_recommendation": "publish",
    "confidence": 0.9,
}


def test_combined_generation_requires_draft_for_publishable_content():
    with pytest.raises(ValidationError):
        PostGenerationContent.model_validate({"analysis": ANALYSIS, "draft": None})


def test_combined_prompt_requests_analysis_and_draft_together():
    messages = post_generation_messages(
        {"title": "신곡 공개", "text": "공식 영상이 공개됐다."},
        {"display_name": "팬AI", "role": "fan", "tone": "따뜻함", "system_prompt": "사실만 쓴다."},
    )
    assert '"analysis"' in messages[1]["content"]
    assert '"draft"' in messages[1]["content"]


def test_generated_tags_are_stored_without_hash_prefixes_or_duplicates():
    content = PostGenerationContent.model_validate(
        {
            "analysis": ANALYSIS,
            "draft": {
                "title": "신곡 공개",
                "body": "공식 영상이 공개됐다.",
                "tags": ["#아이유", "##KPOP", "아이유", "  #신곡  ", ""],
                "risk_flags": [],
                "confidence": 0.9,
            },
        }
    )

    assert content.draft.tags == ["아이유", "KPOP", "신곡"]


def test_manual_work_defers_background_work():
    coordinator = LLMWorkCoordinator()
    with coordinator.manual():
        with coordinator.background() as acquired:
            assert acquired is False
