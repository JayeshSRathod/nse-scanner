"""Environment-driven provider construction."""

from __future__ import annotations

import os

from .base import LLMProvider, ProviderError
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider


def build_provider(name: str | None = None) -> LLMProvider:
    provider = (name or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
    timeout = int(os.getenv("PORTFOLIO_REVIEW_TIMEOUT_SECONDS", "90"))

    if provider == "gemini":
        return GeminiProvider(
            api_key=os.getenv("GEMINI_API_KEY", ""),
            model=os.getenv("GEMINI_MODEL", os.getenv("LLM_MODEL", "gemini-2.0-flash")),
            timeout=timeout,
        )
    if provider == "groq":
        return GroqProvider(
            api_key=os.getenv("GROQ_API_KEY", ""),
            model=os.getenv("GROQ_MODEL", os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")),
            timeout=timeout,
        )
    raise ProviderError(f"Unsupported LLM provider: {provider}")
