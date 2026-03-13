PROFILES: dict[str, dict[str, str]] = {
    "ai_detection": {
        "description": "Estimate whether a text appears AI assisted.",
    },
    "humanization_feedback": {
        "description": "Provide signals for making text sound more human.",
    },
}


def is_supported_profile(profile: str) -> bool:
    return profile in PROFILES
