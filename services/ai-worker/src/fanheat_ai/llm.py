import json
from typing import TypeVar

import httpx
from pydantic import BaseModel

from .config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self.timeout = settings.llm_timeout_seconds

    def generate_json(self, messages: list[dict[str, str]], response_model: type[T]) -> T:
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": response_model.model_json_schema(),
                "think": False,
                "keep_alive": "30m",
                "options": {"temperature": 0.2, "num_predict": 1200},
            }
            response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            if response.status_code == 400 and "failed to parse grammar" in response.text.lower():
                # Some native Ollama/llama.cpp combinations reject valid JSON Schema
                # constraints. Keep native acceleration and fall back to JSON mode;
                # Pydantic below remains the source of truth for validation.
                payload["format"] = "json"
                response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
            content = response.json().get("message", {}).get("content")
            if not isinstance(content, str):
                raise LLMError("Ollama response did not contain message.content")
            return response_model.model_validate(json.loads(content))
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            detail = ""
            if isinstance(exc, httpx.HTTPStatusError):
                detail = f" · {exc.response.text[:500]}"
            raise LLMError(f"local LLM request failed: {exc}{detail}") from exc

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return response.is_success
        except httpx.HTTPError:
            return False
