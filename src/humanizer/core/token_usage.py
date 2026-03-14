from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class TokenUsageRecord:
    provider: str
    model: str
    operation: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class TokenUsageLogger:
    def __init__(self, path: str, enabled: bool = True):
        self._path = Path(path)
        self._enabled = enabled

    def log(self, record: TokenUsageRecord) -> None:
        if not self._enabled:
            return
        payload = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "provider": record.provider,
            "model": record.model,
            "operation": record.operation,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "total_tokens": record.total_tokens,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True))
                handle.write("\n")
        except OSError:
            return

    def log_response(
        self,
        provider: str,
        model: str,
        operation: str,
        response_payload: dict[str, object],
    ) -> None:
        record = extract_token_usage(provider, model, operation, response_payload)
        if record is None:
            return
        self.log(record)


def extract_token_usage(
    provider: str,
    model: str,
    operation: str,
    response_payload: dict[str, object],
) -> TokenUsageRecord | None:
    if provider == "openai":
        usage = response_payload.get("usage")
        if not isinstance(usage, dict):
            return None
        return TokenUsageRecord(
            provider=provider,
            model=model,
            operation=operation,
            input_tokens=_coerce_int(usage.get("input_tokens")),
            output_tokens=_coerce_int(usage.get("output_tokens")),
            total_tokens=_coerce_int(usage.get("total_tokens")),
        )
    if provider == "gemini":
        usage = response_payload.get("usageMetadata")
        if not isinstance(usage, dict):
            return None
        return TokenUsageRecord(
            provider=provider,
            model=model,
            operation=operation,
            input_tokens=_coerce_int(usage.get("promptTokenCount")),
            output_tokens=_coerce_int(usage.get("candidatesTokenCount")),
            total_tokens=_coerce_int(usage.get("totalTokenCount")),
        )
    if provider == "perplexity":
        usage = response_payload.get("usage")
        if not isinstance(usage, dict):
            return None
        return TokenUsageRecord(
            provider=provider,
            model=model,
            operation=operation,
            input_tokens=_coerce_int(usage.get("prompt_tokens")),
            output_tokens=_coerce_int(usage.get("completion_tokens")),
            total_tokens=_coerce_int(usage.get("total_tokens")),
        )
    if provider == "anthropic":
        usage = response_payload.get("usage")
        if not isinstance(usage, dict):
            return None
        input_tokens = _coerce_int(usage.get("input_tokens"))
        output_tokens = _coerce_int(usage.get("output_tokens"))
        total_tokens = None
        if input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        return TokenUsageRecord(
            provider=provider,
            model=model,
            operation=operation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
    return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
