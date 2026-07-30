"""Groq OpenAI-compatible REST adapter."""

from __future__ import annotations

from .base import LLMProvider, ProviderError, ProviderResponse
from .http_json import decode_json_object, post_json


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: int = 90):
        if not api_key:
            raise ProviderError("GROQ_API_KEY is not configured")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate_review(self, prompt: str) -> ProviderResponse:
        data = post_json(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": self.model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "Return one valid JSON object only."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self.timeout,
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Groq response did not contain generated text") from exc
        return ProviderResponse(decode_json_object(text), self.name, self.model)
