from __future__ import annotations

from time import sleep

import httpx

from humanizer.core.errors import HumanizerError, ProviderTransientError
from humanizer.core.token_usage import TokenUsageLogger
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
    openai_rewrite_review_schema,
    openai_json_schema,
    parse_provider_json,
    parse_rewrite_review_json,
)


class OpenAIAdapter:
    def __init__(
        self,
        api_key: str,
        default_model: str,
        base_url: str,
        timeout_seconds: float,
        retry_attempts: int,
        retry_backoff_seconds: float,
        token_usage_logger: TokenUsageLogger | None = None,
    ):
        self.name = "openai"
        self.default_model = default_model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._token_usage_logger = token_usage_logger

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

        response_payload = self._post_responses(payload, "openai request")
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

        response_payload = self._post_responses(payload, "openai rewrite request")
        output_text = response_payload.get("output_text") or _extract_openai_output_text(response_payload)
        if not output_text:
            raise HumanizerError("openai rewrite response did not include text output")
        return output_text.strip()

    def review_rewrite(self, request: RewriteReviewRequest) -> RewriteReviewResult:
        payload = {
            "model": request.model or self.default_model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": build_rewrite_review_instructions(request.language_hint),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                f"Source text:\n{request.source_text}\n\n"
                                f"Rewritten text:\n{request.rewritten_text}"
                            ),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "humanizer_rewrite_review",
                    "schema": openai_rewrite_review_schema(),
                    "strict": True,
                }
            },
        }

        response_payload = self._post_responses(payload, "openai rewrite review request")
        output_text = response_payload.get("output_text") or _extract_openai_output_text(response_payload)
        if not output_text:
            raise HumanizerError("openai rewrite review response did not include structured output")
        try:
            return parse_rewrite_review_json(output_text)
        except ValueError as exc:
            raise HumanizerError(f"openai rewrite review could not be normalized: {exc}") from exc

    def _post_responses(self, payload: dict[str, object], action_label: str) -> dict[str, object]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        attempts = max(self._retry_attempts, 1)
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(f"{self._base_url}/responses", headers=headers, json=payload)
                    response.raise_for_status()
                    response_payload = response.json()
                    if self._token_usage_logger is not None:
                        self._token_usage_logger.log_response(
                            provider=self.name,
                            model=str(payload.get("model") or self.default_model),
                            operation=action_label,
                            response_payload=response_payload,
                        )
                    return response_payload
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
