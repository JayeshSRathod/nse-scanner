"""Shared HTTP/JSON helpers for REST-based LLM providers."""

from __future__ import annotations

import json
from typing import Any

import requests

from .base import ProviderError


def post_json(url: str, *, headers: dict[str, str], body: dict[str, Any], timeout: int) -> dict[str, Any]:
    try:
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ProviderError(f"LLM HTTP request failed: {exc}") from exc

    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError("LLM provider returned non-JSON HTTP content") from exc


def decode_json_object(text: str) -> dict[str, Any]:
    """Decode a JSON object, tolerating fenced JSON but no prose."""
    cleaned = text.strip()
    if cleaned.startswith("```json") and cleaned.endswith("```"):
        cleaned = cleaned[7:-3].strip()
    elif cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned[3:-3].strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"LLM response is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ProviderError("LLM response must be a JSON object")
    return payload
