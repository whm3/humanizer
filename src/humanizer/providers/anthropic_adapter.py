from __future__ import annotations

import logging
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
    parse_provider_json,
    parse_rewrite_review_json,
)


logger = logging.getLogger(__name__)


class AnthropicAdapter:
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
        self.name = "anthropic"
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
            "max_tokens": 512,
            "system": build_analysis_instructions(request),
            "messages": [{"role": "user", "content": request.text}],
        }

        response_payload = self._post_messages(model, payload, "anthropic analyze request")
        output_text = _extract_anthropic_output_text(response_payload)
        if not output_text:
            raise HumanizerError("anthropic response did not include structured output text")
        try:
            return parse_provider_json(request.profile_name, output_text)
        except ValueError as exc:
            raise HumanizerError(f"anthropic response could not be normalized: {exc}") from exc

    def rewrite(self, request: RewriteRequest) -> str:
        model = request.model or self.default_model
        payload = {
            "model": model,
            "max_tokens": 2048,
            "system": build_rewrite_instructions(request),
            "messages": [{"role": "user", "content": request.text}],
        }

        response_payload = self._post_messages(model, payload, "anthropic rewrite request")
        output_text = _extract_anthropic_output_text(response_payload)
        if not output_text:
            raise HumanizerError("anthropic rewrite response did not include text output")
        return output_text.strip()

    def review_rewrite(self, request: RewriteReviewRequest) -> RewriteReviewResult:
        model = request.model or self.default_model
        payload = {
            "model": model,
            "max_tokens": 512,
            "system": build_rewrite_review_instructions(request.language_hint),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Source text:\n{request.source_text}\n\n"
                        f"Rewritten text:\n{request.rewritten_text}"
                    ),
                }
            ],
        }

        response_payload = self._post_messages(
            model,
            payload,
            "anthropic rewrite review request",
        )
        output_text = _extract_anthropic_output_text(response_payload)
        if not output_text:
            raise HumanizerError("anthropic rewrite review response did not include structured output")
        try:
            return parse_rewrite_review_json(output_text)
        except ValueError as exc:
            raise HumanizerError(f"anthropic rewrite review could not be normalized: {exc}") from exc

    def _post_messages(
        self,
        model: str,
        payload: dict[str, object],
        action_label: str,
    ) -> dict[str, object]:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        attempts = max(self._retry_attempts, 1)
        for attempt in range(1, attempts + 1):
            try:
                logger.debug("provider.request provider=%s action=%s model=%s attempt=%d", self.name, action_label, model, attempt)
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(
                        f"{self._base_url}/v1/messages",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    response_payload = response.json()
                    if self._token_usage_logger is not None:
                        self._token_usage_logger.log_response(
                            provider=self.name,
                            model=model,
                            operation=action_label,
                            response_payload=response_payload,
                        )
                    return response_payload
            except httpx.HTTPStatusError as exc:
                logger.warning("provider.http_error provider=%s action=%s status=%d attempt=%d", self.name, action_label, exc.response.status_code, attempt)
                if exc.response.status_code == 429 and attempt < attempts:
                    sleep(self._retry_backoff_seconds * attempt)
                    continue
                if exc.response.status_code in {429, 500, 502, 503, 504, 529}:
                    raise ProviderTransientError(f"{action_label} temporarily unavailable: {exc}") from exc
                raise HumanizerError(f"{action_label} failed: {exc}") from exc
            except httpx.HTTPError as exc:
                if attempt < attempts:
                    sleep(self._retry_backoff_seconds * attempt)
                    continue
                raise ProviderTransientError(f"{action_label} temporarily unavailable: {exc}") from exc
        raise ProviderTransientError(f"{action_label} temporarily unavailable")


def _extract_anthropic_output_text(response_payload: dict[str, object]) -> str:
    content = response_payload.get("content")
    if not isinstance(content, list):
        return ""
    text_parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text)
    return "\n".join(text_parts).strip()
