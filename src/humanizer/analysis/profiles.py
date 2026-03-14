from __future__ import annotations

from dataclasses import dataclass

from humanizer.core.errors import ValidationError


@dataclass(frozen=True)
class AnalysisProfile:
    name: str
    description: str
    system_prompt: str
    default_temperature: float
    supported_providers: tuple[str, ...]


PROFILES: dict[str, AnalysisProfile] = {
    "ai_detection": AnalysisProfile(
        name="ai_detection",
        description="Estimate whether a text appears AI assisted.",
        system_prompt=(
            "Classify the text for likely AI assistance and return normalized scoring signals."
        ),
        default_temperature=0.1,
        supported_providers=("anthropic", "gemini", "openai", "perplexity"),
    ),
    "humanization_feedback": AnalysisProfile(
        name="humanization_feedback",
        description="Provide signals for making text sound more human.",
        system_prompt=(
            "Review the text for humanization opportunities and return structured style signals."
        ),
        default_temperature=0.3,
        supported_providers=("anthropic", "gemini", "openai", "perplexity"),
    ),
}


def get_profile(profile_name: str) -> AnalysisProfile:
    try:
        return PROFILES[profile_name]
    except KeyError as exc:
        raise ValidationError(f"unsupported profile: {profile_name}") from exc


def list_profiles() -> list[AnalysisProfile]:
    return list(PROFILES.values())
