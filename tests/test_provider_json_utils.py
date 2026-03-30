from humanizer.providers.base import RewriteRequest
from humanizer.providers.json_utils import build_rewrite_instructions, parse_provider_json


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


def test_build_rewrite_instructions_allows_structural_change_without_new_facts() -> None:
    instructions = build_rewrite_instructions(
        RewriteRequest(
            text="Example source.",
            language_hint="en",
            content_type="text",
            model="gpt-5-mini",
            changes=["break up repeated motivational phrasing"],
            signals=["tidy parallel constructions"],
            iteration=2,
            prior_score=0.82,
            target_score=0.40,
            metadata={},
        )
    )
    lowered = instructions.lower()

    assert "merge, split, reorder, or shorten nearby sentences" in lowered
    assert "do not introduce any new factual claims" in lowered
    assert "do not preserve the original sentence-by-sentence cadence" in lowered
