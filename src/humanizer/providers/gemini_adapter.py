from __future__ import annotations

import httpx

from humanizer.core.errors import HumanizerError
from humanizer.providers.base import ProviderRequest, ProviderResult, RewriteRequest
from humanizer.providers.json_utils import (
    build_analysis_instructions,
    build_rewrite_instructions,
    gemini_response_schema,
    parse_provider_json,
)


class GeminiAdapter:
    def __init__(self, api_key: str, default_model: str, base_url: str, timeout_seconds: float):
        self.name = "gemini"
        self.default_model = default_model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def analyze(self, request: ProviderRequest) -> ProviderResult:
        model = request.model or self.default_model
        payload = {
            "systemInstruction": {"parts": [{"text": build_analysis_instructions(request)}]},
            "contents": [{"role": "user", "parts": [{"text": request.text}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "responseSchema": gemini_response_schema(request.profile_name),
            },
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/models/{model}:generateContent",
                    params={"key": self._api_key},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HumanizerError(f"gemini request failed: {exc}") from exc

        response_payload = response.json()
        output_text = _extract_gemini_output_text(response_payload)
        if not output_text:
            raise HumanizerError("gemini response did not include structured output text")
        try:
            return parse_provider_json(request.profile_name, output_text)
        except ValueError as exc:
            raise HumanizerError(f"gemini response could not be normalized: {exc}") from exc

    def rewrite(self, request: RewriteRequest) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": build_rewrite_instructions(request)}]},
            "contents": [{"role": "user", "parts": [{"text": request.text}]}],
            "generationConfig": {
                "temperature": 0.8,
            },
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/models/{request.model or self.default_model}:generateContent",
                    params={"key": self._api_key},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HumanizerError(f"gemini rewrite request failed: {exc}") from exc

        response_payload = response.json()
        output_text = _extract_gemini_output_text(response_payload)
        if not output_text:
            raise HumanizerError("gemini rewrite response did not include text output")
        return output_text.strip()


def _extract_gemini_output_text(response_payload: dict[str, object]) -> str:
    candidates = response_payload.get("candidates")
    if not isinstance(candidates, list):
        return ""
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            if isinstance(part.get("text"), str):
                return part["text"]
    return ""
