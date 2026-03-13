from __future__ import annotations

from humanizer.providers.base import ProviderAdapter, ProviderRequest, ProviderResult


class HeuristicAdapter(ProviderAdapter):
    """Local deterministic adapter used until live provider transports are added."""

    def __init__(self, name: str):
        self.name = name

    def analyze(self, request: ProviderRequest) -> ProviderResult:
        words = request.text.split()
        word_count = max(len(words), 1)
        avg_word_len = sum(len(word.strip(".,!?")) for word in words) / word_count
        sentence_count = max(
            request.text.count(".") + request.text.count("!") + request.text.count("?"),
            1,
        )
        sentence_density = word_count / sentence_count

        if request.profile_name == "humanization_feedback":
            needs_humanization = avg_word_len > 4.8 or sentence_density > 18
            return ProviderResult(
                label="needs_humanization" if needs_humanization else "naturally_varied",
                score=0.67 if needs_humanization else 0.33,
                confidence="medium",
                signals=[
                    "high structural regularity" if avg_word_len > 4.8 else "good lexical variation",
                    "sentence rhythm looks dense" if sentence_density > 18 else "sentence rhythm looks varied",
                ],
                explanation="Deterministic local heuristic used as a temporary adapter.",
            )

        likely_ai = avg_word_len > 4.7 or sentence_density > 20
        return ProviderResult(
            label="likely_ai_assisted" if likely_ai else "likely_human",
            score=0.72 if likely_ai else 0.28,
            confidence="medium",
            signals=[
                "high structural regularity" if avg_word_len > 4.7 else "higher lexical variation",
                "dense sentence packing" if sentence_density > 20 else "looser sentence cadence",
            ],
            explanation="Deterministic local heuristic used as a temporary adapter.",
        )
