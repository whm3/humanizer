from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import AnalyzeRequest, HumanizeRequest
from humanizer.core.settings import Settings
from humanizer.providers.registry import build_provider_registry

ALL_STUB_PROVIDERS = {"anthropic", "deepseek", "gemini", "grok", "openai", "perplexity"}


def test_analyze_returns_result_with_defaults() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    result = service.analyze(AnalyzeRequest(text="A basic sentence for testing.", profile="ai_detection"))

    assert set(result.selected_providers) == ALL_STUB_PROVIDERS
    assert result.profile == "ai_detection"
    assert result.latency_ms >= 1
    assert result.worst_case.provider in ALL_STUB_PROVIDERS
    assert set(result.consensus.providers_considered) == ALL_STUB_PROVIDERS
    assert "detections" in result.summary.model_dump()
    assert len(result.summary.humanization_changes) >= 1


def test_analyze_humanization_profile_returns_expected_label_space() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    result = service.analyze(
        AnalyzeRequest(
            text="Elaborately articulated phraseology increases the average lexical footprint.",
            profile="humanization_feedback",
        )
    )

    assert result.consensus.label in {"needs_humanization", "naturally_varied"}
    assert len(result.consensus.signals) >= 1
    assert len(result.summary.humanization_changes) >= 1


def test_analyze_rejects_disabled_provider() -> None:
    settings = Settings(enable_provider_openai=False, allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    try:
        service.analyze(AnalyzeRequest(text="test", profile="ai_detection", provider="openai"))
    except ValueError as exc:
        assert str(exc) == "unsupported or disabled provider: openai"
    else:
        raise AssertionError("expected ValueError for disabled provider")


def test_analyze_rejects_text_that_exceeds_limit() -> None:
    settings = Settings(request_text_max_chars=10, allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    try:
        service.analyze(AnalyzeRequest(text="this text is too long", profile="ai_detection"))
    except ValueError as exc:
        assert str(exc) == "text exceeds configured limit"
    else:
        raise AssertionError("expected ValueError for oversized text")


def test_batch_analysis_returns_mixed_results_without_failing_whole_batch() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    results = service.analyze_batch(
        [
            AnalyzeRequest(text="Short text", profile="ai_detection"),
            AnalyzeRequest(text="Other text", profile="nope"),
        ]
    )

    assert results[0].status == "success"
    assert results[1].status == "error"


def test_list_providers_reflects_enabled_registry() -> None:
    settings = Settings(
        enable_provider_perplexity=False,
        enable_provider_gemini=False,
        enable_provider_grok=False,
        enable_provider_deepseek=False,
        enable_provider_anthropic=False,
        allow_stub_providers_without_keys=True,
    )
    service = AnalysisService(settings, build_provider_registry(settings))

    providers = service.list_providers()

    assert providers == [{"name": "openai", "enabled": True, "default_model": "gpt-5-mini"}]


def test_analyze_single_provider_override_returns_only_requested_source() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    result = service.analyze(
        AnalyzeRequest(text="Single provider path.", profile="ai_detection", provider="openai")
    )

    assert result.selected_providers == ["openai"]
    assert len(result.source_results) == 1
    assert result.worst_case.provider == "openai"


def test_humanize_until_threshold_rewrites_text_and_returns_final_analysis() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    result = service.humanize_until_threshold(
        HumanizeRequest(
            text="Furthermore, individuals utilize numerous repetitive phrases in order to communicate.",
            threshold=0.40,
            max_iterations=2,
        )
    )

    assert result.rewritten_text
    assert len(result.iterations) >= 1
    assert result.final_analysis.profile == "ai_detection"


def test_analyze_detects_code_content_and_disables_humanization_summary() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    result = service.analyze(
        AnalyzeRequest(
            text="import os\n\ndef main():\n    return os.getcwd()\n",
            profile="ai_detection",
        )
    )

    assert result.content_type == "code"
    assert result.summary.humanization_changes == []


def test_humanize_rejects_code_inputs() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    try:
        service.humanize_until_threshold(
            HumanizeRequest(
                text="import os\n\ndef main():\n    return os.getcwd()\n",
                profile="ai_detection",
            )
        )
    except ValueError as exc:
        assert str(exc) == "humanization is disabled for source code inputs"
    else:
        raise AssertionError("expected ValueError for code humanization")


def test_humanize_preserves_fenced_code_blocks_inside_prose_documents() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))
    text = (
        "This whitepaper section is overly formal and repetitive.\n\n"
        "```python\nimport os\n\ndef main():\n    return os.getcwd()\n```\n\n"
        "Furthermore, individuals utilize numerous repetitive phrases in order to communicate."
    )

    result = service.humanize_until_threshold(
        HumanizeRequest(
            text=text,
            profile="ai_detection",
            threshold=0.40,
            max_iterations=2,
        )
    )

    assert "```python\nimport os\n\ndef main():\n    return os.getcwd()\n```" in result.rewritten_text
