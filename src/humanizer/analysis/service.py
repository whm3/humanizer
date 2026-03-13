from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from humanizer.analysis.profiles import is_supported_profile
from humanizer.api.schemas import AnalyzeRequest, AnalyzeResult, BatchAnalyzeItemResponse
from humanizer.core.settings import Settings


class AnalysisService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResult:
        if len(request.text) > self.settings.request_text_max_chars:
            raise ValueError("text exceeds configured limit")
        if not is_supported_profile(request.profile):
            raise ValueError(f"unsupported profile: {request.profile}")

        provider = request.provider or self.settings.default_provider
        if provider == "openai" and not self.settings.enable_provider_openai:
            raise ValueError("provider disabled: openai")
        if provider == "perplexity" and not self.settings.enable_provider_perplexity:
            raise ValueError("provider disabled: perplexity")
        if provider not in {"openai", "perplexity"}:
            raise ValueError(f"unsupported provider: {provider}")

        model = request.model or self.settings.default_model
        started = perf_counter()
        label, score, confidence, signals = self._score(request.text, request.profile)
        latency_ms = max(1, int((perf_counter() - started) * 1000))

        return AnalyzeResult(
            profile=request.profile,
            label=label,
            score=score,
            confidence=confidence,
            signals=signals,
            provider=provider,
            model=model,
            request_id=f"req_{uuid4().hex[:12]}",
            latency_ms=latency_ms,
        )

    def analyze_batch(self, items: list[AnalyzeRequest]) -> list[BatchAnalyzeItemResponse]:
        if len(items) > self.settings.batch_max_items:
            raise ValueError("batch exceeds configured limit")

        results: list[BatchAnalyzeItemResponse] = []
        for item in items:
            try:
                results.append(BatchAnalyzeItemResponse(status="success", result=self.analyze(item)))
            except ValueError as exc:
                results.append(BatchAnalyzeItemResponse(status="error", error=str(exc)))
        return results

    def list_providers(self) -> list[dict[str, str | bool]]:
        return [
            {
                "name": "openai",
                "enabled": self.settings.enable_provider_openai,
                "default_model": self.settings.default_model,
            },
            {
                "name": "perplexity",
                "enabled": self.settings.enable_provider_perplexity,
                "default_model": self.settings.default_model,
            },
        ]

    def _score(self, text: str, profile: str) -> tuple[str, float, str, list[str]]:
        word_count = len(text.split())
        avg_word_len = sum(len(word.strip(".,!?")) for word in text.split()) / max(word_count, 1)
        signal = "high structural regularity" if avg_word_len > 4.5 else "higher lexical variation"

        if profile == "humanization_feedback":
            return (
                "needs_humanization" if avg_word_len > 4.8 else "naturally_varied",
                0.66 if avg_word_len > 4.8 else 0.31,
                "medium",
                [signal, "sentence rhythm estimate generated locally"],
            )

        return (
            "likely_ai_assisted" if avg_word_len > 4.7 else "likely_human",
            0.72 if avg_word_len > 4.7 else 0.28,
            "medium",
            [signal, "baseline heuristic score"],
        )
