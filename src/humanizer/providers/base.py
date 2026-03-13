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


class ProviderAdapter(Protocol):
    name: str

    def analyze(self, request: ProviderRequest) -> ProviderResult:
        ...
