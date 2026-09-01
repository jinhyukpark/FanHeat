import respx
from httpx import Response

from fanheat_ai.config import Settings
from fanheat_ai.llm import OllamaClient
from fanheat_ai.schemas import EnrichmentResult


@respx.mock
def test_generate_json_validates_structured_response():
    route = respx.post("http://ollama:11434/api/chat").mock(
        return_value=Response(
            200,
            json={
                "message": {
                    "content": (
                        '{"language":"ko","artist":"IU","topic":"release",'
                        '"sentiment":"positive","toxicity":0,"importance":0.8,'
                        '"summary":"새 영상이 공개됐다.","publish_recommendation":"publish",'
                        '"confidence":0.9}'
                    )
                }
            },
        )
    )
    client = OllamaClient(Settings(ollama_base_url="http://ollama:11434"))
    result = client.generate_json([{"role": "user", "content": "test"}], EnrichmentResult)
    assert result.artist == "IU"
    assert result.publish_recommendation == "publish"
    payload = __import__("json").loads(route.calls.last.request.content)
    assert payload["think"] is False
    assert payload["keep_alive"] == "30m"
    assert payload["options"]["num_predict"] == 1200


@respx.mock
def test_generate_json_falls_back_when_native_ollama_rejects_schema_grammar():
    route = respx.post("http://ollama:11434/api/chat").mock(
        side_effect=[
            Response(400, json={"error": "Failed to initialize samplers: failed to parse grammar"}),
            Response(
                200,
                json={
                    "message": {
                        "content": (
                            '{"language":"ko","artist":"IU","topic":"release",'
                            '"sentiment":"positive","toxicity":0,"importance":0.8,'
                            '"summary":"새 영상이 공개됐다.","publish_recommendation":"publish",'
                            '"confidence":0.9}'
                        )
                    }
                },
            ),
        ]
    )
    client = OllamaClient(Settings(ollama_base_url="http://ollama:11434"))
    result = client.generate_json([{"role": "user", "content": "test"}], EnrichmentResult)

    assert result.artist == "IU"
    assert route.call_count == 2
    first_payload = __import__("json").loads(route.calls[0].request.content)
    fallback_payload = __import__("json").loads(route.calls[1].request.content)
    assert isinstance(first_payload["format"], dict)
    assert fallback_payload["format"] == "json"
