from __future__ import annotations

import httpx

from humanizer.core.errors import HumanizerError
from humanizer.providers.base import ProviderRequest, ProviderResult, RewriteRequest
from humanizer.providers.json_utils import (
    build_analysis_instructions,
    build_rewrite_instructions,
    parse_provider_json,
)


class PerplexityAdapter:
    def __init__(self, api_key: str, default_model: str, base_url: str, timeout_seconds: float):
        self.name = "perplexity"
        self.default_model = default_model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def analyze(self, request: ProviderRequest) -> ProviderResult:
        model = request.model or self.default_model
        payload = {
            "model": model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": build_analysis_instructions(request)},
                {"role": "user", "content": request.text},
            ],
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HumanizerError(f"perplexity request failed: {exc}") from exc

        response_payload = response.json()
        output_text = _extract_perplexity_output_text(response_payload)
        if not output_text:
            raise HumanizerError("perplexity response did not include message content")
        try:
            return parse_provider_json(request.profile_name, output_text)
        except ValueError as exc:
            raise HumanizerError(f"perplexity response could not be normalized: {exc}") from exc

    def rewrite(self, request: RewriteRequest) -> str:
        payload = {
            "model": request.model or self.default_model,
            "temperature": 0.8,
            "messages": [
                {"role": "system", "content": build_rewrite_instructions(request)},
                {"role": "user", "content": request.text},
            ],
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HumanizerError(f"perplexity rewrite request failed: {exc}") from exc

        response_payload = response.json()
        output_text = _extract_perplexity_output_text(response_payload)
        if not output_text:
            raise HumanizerError("perplexity rewrite response did not include text output")
        return output_text.strip()


def _extract_perplexity_output_text(response_payload: dict[str, object]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list):
        return ""
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        if isinstance(message.get("content"), str):
            return message["content"]
    return ""
