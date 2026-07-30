"""Base contracts for portfolio-review LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class ProviderError(RuntimeError):
    """Raised when a configured LLM provider cannot return a usable response."""


@dataclass(frozen=True)
class ProviderResponse:
    payload: dict[str, Any]
    provider: str
    model: str


class LLMProvider(ABC):
    """Minimal provider interface used by the review runner."""

    name: str
    model: str

    @abstractmethod
    def generate_review(self, prompt: str) -> ProviderResponse:
        """Return one decoded JSON review or raise ProviderError."""
        raise NotImplementedError
