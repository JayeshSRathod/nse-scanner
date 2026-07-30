"""Gemini REST adapter using JSON response mode."""

from __future__ import annotations

from .base import LLMProvider, ProviderError, ProviderResponse
from .http_json import decode_json_object, post_json


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: int = 90):
        if not api_key:
            raise ProviderError("GEMINI_API_KEY is not configured")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate_review(self, prompt: str) -> ProviderResponse:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        data = post_json(url, headers={"Content-Type": "application/json"}, body=body, timeout=self.timeout)
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Gemini response did not contain generated text") from exc
        return ProviderResponse(decode_json_object(text), self.name, self.model)
