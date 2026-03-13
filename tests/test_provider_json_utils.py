from humanizer.providers.json_utils import parse_provider_json


def test_parse_provider_json_inverts_human_confidence_style_scores_for_ai_detection() -> None:
    result = parse_provider_json(
        "ai_detection",
        """
        {
          "label": "likely_human",
          "score": 0.92,
          "confidence": "high",
          "signals": ["canonical historical text"],
          "explanation": "Human-authored."
        }
        """,
    )

    assert result.label == "likely_human"
    assert result.score == 0.08


def test_parse_provider_json_preserves_aligned_scores_for_ai_detection() -> None:
    result = parse_provider_json(
        "ai_detection",
        """
        {
          "label": "likely_ai_assisted",
          "score": 0.81,
          "confidence": "high",
          "signals": ["uniform structure"],
          "explanation": "AI-like."
        }
        """,
    )

    assert result.label == "likely_ai_assisted"
    assert result.score == 0.81
