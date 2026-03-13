from __future__ import annotations

import httpx

from humanizer.core.errors import HumanizerError
from humanizer.providers.base import ProviderRequest, ProviderResult, RewriteRequest
from humanizer.providers.json_utils import (
    build_analysis_instructions,
    build_rewrite_instructions,
    openai_json_schema,
    parse_provider_json,
)


class OpenAIAdapter:
    def __init__(self, api_key: str, default_model: str, base_url: str, timeout_seconds: float):
        self.name = "openai"
        self.default_model = default_model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def analyze(self, request: ProviderRequest) -> ProviderResult:
        model = request.model or self.default_model
        payload = {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": build_analysis_instructions(request),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": request.text}],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "humanizer_provider_result",
                    "schema": openai_json_schema(request.profile_name),
                    "strict": True,
                }
            },
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/responses",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HumanizerError(f"openai request failed: {exc}") from exc

        response_payload = response.json()
        output_text = response_payload.get("output_text") or _extract_openai_output_text(response_payload)
        if not output_text:
            raise HumanizerError("openai response did not include structured output text")
        try:
            return parse_provider_json(request.profile_name, output_text)
        except ValueError as exc:
            raise HumanizerError(f"openai response could not be normalized: {exc}") from exc

    def rewrite(self, request: RewriteRequest) -> str:
        payload = {
            "model": request.model or self.default_model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": build_rewrite_instructions(request),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": request.text}],
                },
            ],
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/responses",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HumanizerError(f"openai rewrite request failed: {exc}") from exc

        response_payload = response.json()
        output_text = response_payload.get("output_text") or _extract_openai_output_text(response_payload)
        if not output_text:
            raise HumanizerError("openai rewrite response did not include text output")
        return output_text.strip()


def _extract_openai_output_text(response_payload: dict[str, object]) -> str:
    output = response_payload.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if isinstance(part.get("text"), str):
                return part["text"]
    return ""
