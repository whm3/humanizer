from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import AnalyzeRequest
from humanizer.core.settings import Settings


def test_analyze_returns_result_with_defaults() -> None:
    service = AnalysisService(Settings())

    result = service.analyze(AnalyzeRequest(text="A basic sentence for testing.", profile="ai_detection"))

    assert result.provider == "openai"
    assert result.model == "gpt-5-mini"
    assert result.profile == "ai_detection"
    assert result.latency_ms >= 1


def test_analyze_humanization_profile_returns_expected_label_space() -> None:
    service = AnalysisService(Settings())

    result = service.analyze(
        AnalyzeRequest(
            text="Elaborately articulated phraseology increases the average lexical footprint.",
            profile="humanization_feedback",
        )
    )

    assert result.label in {"needs_humanization", "naturally_varied"}
    assert len(result.signals) >= 1


def test_analyze_rejects_disabled_provider() -> None:
    settings = Settings(enable_provider_openai=False)
    service = AnalysisService(settings)

    try:
        service.analyze(AnalyzeRequest(text="test", profile="ai_detection", provider="openai"))
    except ValueError as exc:
        assert str(exc) == "provider disabled: openai"
    else:
        raise AssertionError("expected ValueError for disabled provider")


def test_analyze_rejects_text_that_exceeds_limit() -> None:
    settings = Settings(request_text_max_chars=10)
    service = AnalysisService(settings)

    try:
        service.analyze(AnalyzeRequest(text="this text is too long", profile="ai_detection"))
    except ValueError as exc:
        assert str(exc) == "text exceeds configured limit"
    else:
        raise AssertionError("expected ValueError for oversized text")


def test_batch_analysis_returns_mixed_results_without_failing_whole_batch() -> None:
    service = AnalysisService(Settings())

    results = service.analyze_batch(
        [
            AnalyzeRequest(text="Short text", profile="ai_detection"),
            AnalyzeRequest(text="Other text", profile="nope"),
        ]
    )

    assert results[0].status == "success"
    assert results[1].status == "error"
