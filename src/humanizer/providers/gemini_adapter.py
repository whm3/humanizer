from __future__ import annotations

from time import sleep

import httpx

from humanizer.core.errors import HumanizerError, ProviderTransientError
from humanizer.providers.base import (
    ProviderRequest,
    ProviderResult,
    RewriteRequest,
    RewriteReviewRequest,
    RewriteReviewResult,
)
from humanizer.providers.json_utils import (
    build_analysis_instructions,
    build_rewrite_instructions,
    build_rewrite_review_instructions,
    gemini_response_schema,
    gemini_rewrite_review_schema,
    parse_provider_json,
    parse_rewrite_review_json,
)


class GeminiAdapter:
    def __init__(
        self,
        api_key: str,
        default_model: str,
        base_url: str,
        timeout_seconds: float,
        retry_attempts: int,
        retry_backoff_seconds: float,
    ):
        self.name = "gemini"
        self.default_model = default_model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts
        self._retry_backoff_seconds = retry_backoff_seconds

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

        response_payload = self._generate_content(model, payload, "gemini request")
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

        response_payload = self._generate_content(
            request.model or self.default_model,
            payload,
            "gemini rewrite request",
        )
        output_text = _extract_gemini_output_text(response_payload)
        if not output_text:
            raise HumanizerError("gemini rewrite response did not include text output")
        return output_text.strip()

    def review_rewrite(self, request: RewriteReviewRequest) -> RewriteReviewResult:
        payload = {
            "systemInstruction": {
                "parts": [{"text": build_rewrite_review_instructions(request.language_hint)}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"Source text:\n{request.source_text}\n\n"
                                f"Rewritten text:\n{request.rewritten_text}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
                "responseSchema": gemini_rewrite_review_schema(),
            },
        }

        response_payload = self._generate_content(
            request.model or self.default_model,
            payload,
            "gemini rewrite review request",
        )
        output_text = _extract_gemini_output_text(response_payload)
        if not output_text:
            raise HumanizerError("gemini rewrite review response did not include structured output")
        try:
            return parse_rewrite_review_json(output_text)
        except ValueError as exc:
            raise HumanizerError(f"gemini rewrite review could not be normalized: {exc}") from exc

    def _generate_content(
        self,
        model: str,
        payload: dict[str, object],
        action_label: str,
    ) -> dict[str, object]:
        attempts = max(self._retry_attempts, 1)
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(
                        f"{self._base_url}/models/{model}:generateContent",
                        params={"key": self._api_key},
                        json=payload,
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < attempts:
                    sleep(self._retry_backoff_seconds * attempt)
                    continue
                if exc.response.status_code in {429, 500, 502, 503, 504}:
                    raise ProviderTransientError(f"{action_label} temporarily unavailable: {exc}") from exc
                raise HumanizerError(f"{action_label} failed: {exc}") from exc
            except httpx.HTTPError as exc:
                if attempt < attempts:
                    sleep(self._retry_backoff_seconds * attempt)
                    continue
                raise ProviderTransientError(f"{action_label} temporarily unavailable: {exc}") from exc
        raise ProviderTransientError(f"{action_label} temporarily unavailable")


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
