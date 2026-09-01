from fanheat_ai.prompts import comment_messages


def test_comment_prompt_requests_natural_fan_voice():
    messages = comment_messages(
        {"title": "콘서트 직캠", "body": "무대 영상"},
        {
            "id": "5a3652b8-943c-4f3e-a07d-73319d38ce9f",
            "display_name": "응원AI",
            "role": "건강한 응원",
            "tone": "따뜻한 말투",
            "system_prompt": "타 팬덤을 비하하지 않는다.",
        },
    )
    prompt = messages[0]["content"]

    assert "팬 보이스" in prompt
    assert "이모지는 내용에 맞으면 0~2개" in prompt
    assert "기사·보고서 표현" in prompt
    assert "짧은 1~2문장" in prompt
