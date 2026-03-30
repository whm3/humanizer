from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4


@dataclass(frozen=True)
class TokenUsageRecord:
    provider: str
    model: str
    operation: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None = None


@dataclass(frozen=True)
class TokenUsageSummary:
    run_id: str
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
    by_provider: list[dict[str, int | float | str | None]]
    cumulative_calls: int
    cumulative_input_tokens: int
    cumulative_output_tokens: int
    cumulative_total_tokens: int
    cumulative_estimated_cost_usd: float | None


_CURRENT_RUN_ID: ContextVar[str | None] = ContextVar("token_usage_run_id", default=None)

_MODEL_PRICING_USD_PER_MILLION: dict[tuple[str, str], tuple[float, float]] = {
    ("openai", "gpt-5-mini"): (0.25, 2.00),
    ("anthropic", "claude-sonnet-4-5"): (3.00, 15.00),
    ("gemini", "gemini-2.5-flash"): (0.05, 0.20),
    ("perplexity", "sonar"): (1.00, 1.00),
}

_PERPLEXITY_REQUEST_FEE_USD: dict[str, float] = {
    "sonar": 0.005,
}


class TokenUsageLogger:
    def __init__(self, path: str, enabled: bool = True):
        self._path = Path(path)
        self._enabled = enabled
        self._lock = Lock()

    def start_run(self) -> str:
        run_id = f"run_{uuid4().hex[:12]}"
        _CURRENT_RUN_ID.set(run_id)
        return run_id

    def reset(self) -> None:
        """Clear the usage log file. Use between documents or test runs to get
        clean per-document cost accounting instead of cumulative totals."""
        try:
            with self._lock:
                if self._path.exists():
                    self._path.write_text("")
        except OSError:
            return

    def end_run(self, run_id: str) -> TokenUsageSummary:
        summary = self._summarize_run(run_id)
        if self._enabled:
            payload = {
                "event_type": "run_summary",
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "run_id": summary.run_id,
                "calls": summary.calls,
                "input_tokens": summary.input_tokens,
                "output_tokens": summary.output_tokens,
                "total_tokens": summary.total_tokens,
                "estimated_cost_usd": summary.estimated_cost_usd,
                "by_provider": summary.by_provider,
                "cumulative_calls": summary.cumulative_calls,
                "cumulative_input_tokens": summary.cumulative_input_tokens,
                "cumulative_output_tokens": summary.cumulative_output_tokens,
                "cumulative_total_tokens": summary.cumulative_total_tokens,
                "cumulative_estimated_cost_usd": summary.cumulative_estimated_cost_usd,
            }
            self._write(payload)
        if _CURRENT_RUN_ID.get() == run_id:
            _CURRENT_RUN_ID.set(None)
        return summary

    def log(self, record: TokenUsageRecord) -> None:
        if not self._enabled:
            return
        payload = {
            "event_type": "usage",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "run_id": _CURRENT_RUN_ID.get(),
            "provider": record.provider,
            "model": record.model,
            "operation": record.operation,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "total_tokens": record.total_tokens,
            "estimated_cost_usd": record.estimated_cost_usd,
        }
        self._write(payload)

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

    def _write(self, payload: dict[str, object]) -> None:
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, sort_keys=True))
                    handle.write("\n")
        except OSError:
            return

    def _summarize_run(self, run_id: str) -> TokenUsageSummary:
        run_calls = 0
        run_input = 0
        run_output = 0
        run_total = 0
        run_cost = 0.0
        run_has_cost = False
        cumulative_calls = 0
        cumulative_input = 0
        cumulative_output = 0
        cumulative_total = 0
        cumulative_cost = 0.0
        cumulative_has_cost = False
        by_provider: dict[str, dict[str, int | float | str | None]] = {}
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("event_type") != "usage":
                continue
            provider = str(payload.get("provider") or "unknown")
            input_tokens = _coerce_int(payload.get("input_tokens")) or 0
            output_tokens = _coerce_int(payload.get("output_tokens")) or 0
            total_tokens = _coerce_int(payload.get("total_tokens")) or (input_tokens + output_tokens)
            estimated_cost = _coerce_float(payload.get("estimated_cost_usd"))
            cumulative_calls += 1
            cumulative_input += input_tokens
            cumulative_output += output_tokens
            cumulative_total += total_tokens
            if estimated_cost is not None:
                cumulative_cost += estimated_cost
                cumulative_has_cost = True
            if payload.get("run_id") != run_id:
                continue
            run_calls += 1
            run_input += input_tokens
            run_output += output_tokens
            run_total += total_tokens
            if estimated_cost is not None:
                run_cost += estimated_cost
                run_has_cost = True
            provider_bucket = by_provider.setdefault(
                provider,
                {
                    "provider": provider,
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                },
            )
            provider_bucket["calls"] = int(provider_bucket["calls"]) + 1
            provider_bucket["input_tokens"] = int(provider_bucket["input_tokens"]) + input_tokens
            provider_bucket["output_tokens"] = int(provider_bucket["output_tokens"]) + output_tokens
            provider_bucket["total_tokens"] = int(provider_bucket["total_tokens"]) + total_tokens
            if estimated_cost is not None:
                provider_bucket["estimated_cost_usd"] = float(provider_bucket["estimated_cost_usd"]) + estimated_cost
            elif provider_bucket["estimated_cost_usd"] == 0.0:
                provider_bucket["estimated_cost_usd"] = None
        provider_summaries = sorted(by_provider.values(), key=lambda item: str(item["provider"]))
        return TokenUsageSummary(
            run_id=run_id,
            calls=run_calls,
            input_tokens=run_input,
            output_tokens=run_output,
            total_tokens=run_total,
            estimated_cost_usd=round(run_cost, 6) if run_has_cost else None,
            by_provider=provider_summaries,
            cumulative_calls=cumulative_calls,
            cumulative_input_tokens=cumulative_input,
            cumulative_output_tokens=cumulative_output,
            cumulative_total_tokens=cumulative_total,
            cumulative_estimated_cost_usd=round(cumulative_cost, 6) if cumulative_has_cost else None,
        )


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
            estimated_cost_usd=_estimate_cost_usd(
                provider,
                model,
                operation,
                _coerce_int(usage.get("input_tokens")),
                _coerce_int(usage.get("output_tokens")),
            ),
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
            estimated_cost_usd=_estimate_cost_usd(
                provider,
                model,
                operation,
                _coerce_int(usage.get("promptTokenCount")),
                _coerce_int(usage.get("candidatesTokenCount")),
            ),
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
            estimated_cost_usd=_estimate_cost_usd(
                provider,
                model,
                operation,
                _coerce_int(usage.get("prompt_tokens")),
                _coerce_int(usage.get("completion_tokens")),
            ),
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
            estimated_cost_usd=_estimate_cost_usd(
                provider,
                model,
                operation,
                input_tokens,
                output_tokens,
            ),
        )
    if provider == "grok":
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
            estimated_cost_usd=_estimate_cost_usd(
                provider,
                model,
                operation,
                _coerce_int(usage.get("prompt_tokens")),
                _coerce_int(usage.get("completion_tokens")),
            ),
        )
    return None


def _estimate_cost_usd(
    provider: str,
    model: str,
    operation: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    rate = _MODEL_PRICING_USD_PER_MILLION.get((provider, model))
    if rate is None:
        return None
    input_rate, output_rate = rate
    cost = 0.0
    if input_tokens is not None:
        cost += (input_tokens / 1_000_000) * input_rate
    if output_tokens is not None:
        cost += (output_tokens / 1_000_000) * output_rate
    if provider == "perplexity":
        cost += _PERPLEXITY_REQUEST_FEE_USD.get(model, 0.0)
    return round(cost, 6)


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


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
