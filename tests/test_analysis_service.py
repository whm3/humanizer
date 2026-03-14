from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import AnalyzeRequest, HumanizeRequest
from humanizer.core.errors import ProviderTransientError
from humanizer.core.settings import Settings
from humanizer.providers.base import RewriteReviewRequest, RewriteReviewResult
from humanizer.providers.registry import build_provider_registry

ALL_STUB_PROVIDERS = {"anthropic", "gemini", "openai", "perplexity"}


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
    assert result.humanizer_provider == "openai"
    assert result.humanizer_model == "gpt-5-mini"


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


def test_humanize_allows_humanizer_provider_override() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    result = service.humanize_until_threshold(
        HumanizeRequest(
            text="Furthermore, individuals utilize numerous repetitive phrases in order to communicate.",
            threshold=0.40,
            max_iterations=1,
            humanizer_provider="gemini",
            humanizer_model="gemini-2.5-pro",
        )
    )

    assert result.humanizer_provider == "gemini"
    assert result.humanizer_model == "gemini-2.5-pro"


def test_humanize_uses_provider_default_model_when_humanizer_model_is_not_set() -> None:
    settings = Settings(allow_stub_providers_without_keys=True, enable_provider_grok=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    result = service.humanize_until_threshold(
        HumanizeRequest(
            text="This draft feels polished and repetitive in a way that detectors may dislike.",
            threshold=0.40,
            max_iterations=1,
            humanizer_provider="grok",
        )
    )

    assert result.humanizer_provider == "grok"
    assert result.humanizer_model == "grok-3-mini"


def test_analyze_rejects_rewrite_only_provider_for_detection() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    try:
        service.analyze(AnalyzeRequest(text="Single provider path.", profile="ai_detection", provider="grok"))
    except ValueError as exc:
        assert str(exc) == "profile ai_detection does not support provider: grok"
    else:
        raise AssertionError("expected ValueError for rewrite-only provider on detection")


def test_humanization_changes_target_fabricated_technical_style() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    changes = service._humanization_changes(
        "ai_detection",
        [
            "fictional Star Trek technical jargon",
            "synthetic bibliography citing fabricated sources",
            "highly structured whitepaper format",
            "implausible numeric precision",
        ],
    )

    joined_changes = " | ".join(changes).lower()
    assert "invented terminology" in joined_changes or "fabricated citations" in joined_changes


def test_rewrite_guardrails_strip_added_citation_markers() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    guarded = service._apply_rewrite_guardrails(
        "This is a plain paragraph without sources.",
        "This is a rewritten paragraph with invented support [1][3][4].",
        ["openai"],
        "en",
    )

    assert "[1]" not in guarded
    assert "[3]" not in guarded


def test_rewrite_guardrails_require_consensus_for_additions() -> None:
    class ReviewProvider:
        def __init__(self, supported: bool):
            self.name = "reviewer"
            self.default_model = "stub"
            self._supported = supported

        def analyze(self, request):  # pragma: no cover - not used here
            raise AssertionError("analyze should not be called")

        def rewrite(self, request):  # pragma: no cover - not used here
            raise AssertionError("rewrite should not be called")

        def review_rewrite(self, request: RewriteReviewRequest) -> RewriteReviewResult:
            return RewriteReviewResult(
                supported=self._supported,
                confidence="high",
                issues=[] if self._supported else ["unsupported addition"],
                explanation="stub review",
            )

    service = AnalysisService(
        Settings(),
        {"openai": ReviewProvider(True), "gemini": ReviewProvider(False)},
    )

    original = "Registering matters because it shows commitment."
    rewritten = "Registering matters because 18 to 25 year olds must file within 30 days."

    guarded = service._apply_rewrite_guardrails(original, rewritten, ["openai", "gemini"], "en")

    assert guarded == original


def test_rewrite_guardrails_require_secondary_provider_validation() -> None:
    settings = Settings()
    service = AnalysisService(settings, {})

    guarded = service._apply_rewrite_guardrails(
        "This is the original paragraph.",
        "This is the rewritten paragraph.",
        [],
        "en",
    )

    assert guarded == "This is the original paragraph."


def test_rewrite_review_provider_selection_excludes_humanizer_provider() -> None:
    settings = Settings()
    service = AnalysisService(settings, {})

    reviewers = service._select_rewrite_review_providers(
        ["openai", "gemini", "perplexity"],
        "openai",
    )

    assert reviewers == ["gemini", "perplexity"]


def test_safe_fallback_rewrite_makes_source_grounded_structural_changes() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))

    original = (
        "## Introduction\n\n"
        "Furthermore, individuals utilize numerous repetitive phrases in order to communicate.\n\n"
        "This process is not a burden; it is a practical step.\n\n"
        "---\n\n"
        "*Closing Remarks*"
    )

    rewritten = service._apply_safe_fallback_rewrite(
        original,
        [
            "soften overly rigid whitepaper structure and reduce boilerplate formality",
            "break up repeated motivational phrasing and avoid tidy rhetorical contrasts",
        ],
        [
            "formal rhetorical structure",
            "repetitive parallel phrasing",
        ],
    )

    assert "## Introduction" not in rewritten
    assert "---" not in rewritten
    assert "*Closing Remarks*" not in rewritten
    assert "Also, people use many repetitive phrases" in rewritten
    assert "This process isn't a burden. It's a practical step." in rewritten


def test_analyze_skips_temporarily_unavailable_provider_when_others_succeed() -> None:
    class StableProvider:
        def __init__(self, name: str):
            self.name = name
            self.default_model = "stub"

        def analyze(self, request):
            from humanizer.providers.base import ProviderResult

            return ProviderResult(
                label="likely_human",
                score=0.2,
                confidence="medium",
                signals=["plain language"],
                explanation="ok",
            )

        def rewrite(self, request):  # pragma: no cover - not used here
            return request.text

        def review_rewrite(self, request: RewriteReviewRequest) -> RewriteReviewResult:
            return RewriteReviewResult(True, "high", [], "ok")

    class FlakyProvider(StableProvider):
        def analyze(self, request):
            raise ProviderTransientError("rate limited")

    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(
        settings,
        {"openai": StableProvider("openai"), "gemini": FlakyProvider("gemini")},
    )

    result = service.analyze(AnalyzeRequest(text="plain text", profile="ai_detection"))

    assert result.selected_providers == ["openai"]
    assert [item.provider for item in result.source_results] == ["openai"]


def test_analyze_single_provider_override_still_raises_on_transient_failure() -> None:
    class FlakyProvider:
        def __init__(self):
            self.name = "openai"
            self.default_model = "stub"

        def analyze(self, request):
            raise ProviderTransientError("rate limited")

        def rewrite(self, request):  # pragma: no cover - not used here
            return request.text

        def review_rewrite(self, request: RewriteReviewRequest) -> RewriteReviewResult:
            return RewriteReviewResult(True, "high", [], "ok")

    service = AnalysisService(Settings(), {"openai": FlakyProvider()})

    try:
        service.analyze(
            AnalyzeRequest(text="plain text", profile="ai_detection", provider="openai")
        )
    except ProviderTransientError as exc:
        assert "rate limited" in str(exc)
    else:
        raise AssertionError("expected ProviderTransientError for explicit provider override")
