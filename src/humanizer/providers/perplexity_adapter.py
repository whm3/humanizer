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
    parse_provider_json,
    parse_rewrite_review_json,
)


class PerplexityAdapter:
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
        self.name = "perplexity"
        self.default_model = default_model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._token_usage_logger = token_usage_logger

    def analyze(self, request: ProviderRequest) -> ProviderResult:
        model = request.model or self.default_model
        messages = [
            {"role": "system", "content": build_analysis_instructions(request)},
            {"role": "user", "content": request.text},
        ]
        output_text = self._chat(
            model=model,
            messages=messages,
            temperature=0.1,
            action_label="perplexity analyze request",
        )
        if not output_text:
            raise HumanizerError("perplexity response did not include message content")
        try:
            return parse_provider_json(request.profile_name, output_text)
        except ValueError:
            retry_messages = [
                {
                    "role": "system",
                    "content": (
                        f"{build_analysis_instructions(request)}\n"
                        "Your previous response was invalid. Reply with only a raw JSON object."
                    ),
                },
                {"role": "user", "content": request.text},
            ]
            retry_output = self._chat(
                model=model,
                messages=retry_messages,
                temperature=0.0,
                action_label="perplexity analyze retry request",
            )
            if not retry_output:
                raise HumanizerError("perplexity retry response did not include message content")
            try:
                return parse_provider_json(request.profile_name, retry_output)
            except ValueError as exc:
                raise HumanizerError(f"perplexity response could not be normalized: {exc}") from exc

    def rewrite(self, request: RewriteRequest) -> str:
        output_text = self._chat(
            model=request.model or self.default_model,
            messages=[
                {"role": "system", "content": build_rewrite_instructions(request)},
                {"role": "user", "content": request.text},
            ],
            temperature=0.8,
            action_label="perplexity rewrite request",
        )
        if not output_text:
            raise HumanizerError("perplexity rewrite response did not include text output")
        return output_text.strip()

    def review_rewrite(self, request: RewriteReviewRequest) -> RewriteReviewResult:
        model = request.model or self.default_model
        messages = [
            {"role": "system", "content": build_rewrite_review_instructions(request.language_hint)},
            {
                "role": "user",
                "content": (
                    f"Source text:\n{request.source_text}\n\n"
                    f"Rewritten text:\n{request.rewritten_text}"
                ),
            },
        ]
        output_text = self._chat(
            model=model,
            messages=messages,
            temperature=0.0,
            action_label="perplexity rewrite review request",
        )
        if not output_text:
            raise HumanizerError("perplexity rewrite review response did not include text output")
        try:
            return parse_rewrite_review_json(output_text)
        except ValueError:
            retry_messages = [
                {
                    "role": "system",
                    "content": (
                        f"{build_rewrite_review_instructions(request.language_hint)}\n"
                        "Your previous response was invalid. Reply with only a raw JSON object."
                    ),
                },
                messages[1],
            ]
            retry_output = self._chat(
                model=model,
                messages=retry_messages,
                temperature=0.0,
                action_label="perplexity rewrite review retry request",
            )
            if not retry_output:
                raise HumanizerError("perplexity rewrite review retry did not include text output")
            try:
                return parse_rewrite_review_json(retry_output)
            except ValueError as exc:
                raise HumanizerError(f"perplexity rewrite review could not be normalized: {exc}") from exc

    def _chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        action_label: str,
    ) -> str:
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": messages,
        }

        attempts = max(self._retry_attempts, 1)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(
                        f"{self._base_url}/chat/completions",
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
                    return _extract_perplexity_output_text(response_payload)
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
