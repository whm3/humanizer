from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderRequest:
    text: str
    profile_name: str
    language_hint: str
    content_type: str
    system_prompt: str
    model: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class ProviderResult:
    label: str
    score: float
    confidence: str
    signals: list[str]
    explanation: str


@dataclass(frozen=True)
class RewriteRequest:
    text: str
    language_hint: str
    content_type: str
    model: str
    changes: list[str]
    signals: list[str]
    iteration: int
    prior_score: float
    target_score: float
    metadata: dict[str, object]


@dataclass(frozen=True)
class RewriteReviewRequest:
    source_text: str
    rewritten_text: str
    language_hint: str
    model: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class RewriteReviewResult:
    supported: bool
    confidence: str
    issues: list[str]
    explanation: str


class ProviderAdapter(Protocol):
    name: str
    default_model: str

    def analyze(self, request: ProviderRequest) -> ProviderResult:
        ...

    def rewrite(self, request: RewriteRequest) -> str:
        ...

    def review_rewrite(self, request: RewriteReviewRequest) -> RewriteReviewResult:
        ...
