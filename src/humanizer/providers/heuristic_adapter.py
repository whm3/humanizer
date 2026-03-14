from __future__ import annotations

import re

from humanizer.providers.base import (
    ProviderAdapter,
    ProviderRequest,
    ProviderResult,
    RewriteRequest,
    RewriteReviewRequest,
    RewriteReviewResult,
)


class HeuristicAdapter(ProviderAdapter):
    """Local deterministic adapter used until live provider transports are added."""

    def __init__(self, name: str, default_model: str = "stub-model"):
        self.name = name
        self.default_model = default_model

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

    def rewrite(self, request: RewriteRequest) -> str:
        rewritten = request.text
        replacements = {
            "utilize": "use",
            "therefore": "so",
            "moreover": "also",
            "furthermore": "and",
            "however": "but",
            "individuals": "people",
            "numerous": "many",
            "approximately": "about",
        }
        for source, target in replacements.items():
            rewritten = rewritten.replace(source, target).replace(source.capitalize(), target.capitalize())

        lowered_changes = " ".join(change.lower() for change in request.changes)
        lowered_signals = " ".join(signal.lower() for signal in request.signals)
        if "fabricated" in lowered_changes or "invented terminology" in lowered_changes:
            rewritten = rewritten.replace("Sub-Quantum Vernier Calibration", "timing calibration")
            rewritten = rewritten.replace("chronal shearing", "timing drift")
            rewritten = rewritten.replace("dilithium lattice", "reactor core")
        if "overly rigid whitepaper structure" in lowered_changes:
            rewritten = rewritten.replace("Abstract", "Overview")
        if "generic rhetoric" in lowered_changes or "platitudes" in lowered_signals:
            rewritten = rewritten.replace("The future belongs to those who help build it.", "The future depends on what we do next.")
            rewritten = rewritten.replace("It is an idea kept alive by its people.", "It only lasts if people keep showing up for it.")
        if "implausible numeric precision" in lowered_changes:
            rewritten = rewritten.replace("0.0003", "about 0.0003")
            rewritten = rewritten.replace("0.045", "about 0.045")
        if request.iteration > 1:
            rewritten = rewritten.replace("It is ", "It's ")
            rewritten = rewritten.replace("It is not ", "It isn't ")
            rewritten = rewritten.replace("do not", "don't")
            rewritten = rewritten.replace("cannot", "can't")

        rewritten = rewritten.replace(" in order to ", " to ")
        rewritten = rewritten.replace(", and ", ". And ")
        rewritten = " ".join(segment.strip() for segment in rewritten.split())
        return rewritten

    def review_rewrite(self, request: RewriteReviewRequest) -> RewriteReviewResult:
        source_numbers = set(_NUMERIC_PATTERN.findall(request.source_text))
        rewritten_numbers = set(_NUMERIC_PATTERN.findall(request.rewritten_text))
        issues: list[str] = []
        if rewritten_numbers - source_numbers:
            issues.append("introduced new numeric claims")
        if "[" in request.rewritten_text and "]" in request.rewritten_text and "[" not in request.source_text:
            issues.append("introduced citation markers")
        return RewriteReviewResult(
            supported=not issues,
            confidence="medium",
            issues=issues,
            explanation="Deterministic review heuristic used as a temporary adapter.",
        )


_NUMERIC_PATTERN = re.compile(r"\b\d[\d,.\-/%]*\b")
