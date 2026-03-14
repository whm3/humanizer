from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import AnalyzeRequest, BatchAnalyzeRequest, HumanizeRequest
from humanizer.commands import CommandService
from humanizer.core.settings import Settings
from humanizer.providers.registry import build_provider_registry


def build_commands() -> CommandService:
    settings = Settings(allow_stub_providers_without_keys=True)
    service = AnalysisService(settings, build_provider_registry(settings))
    return CommandService(service)


def test_command_health_matches_expected_shape() -> None:
    commands = build_commands()

    payload = commands.health()

    assert payload == {"status": "ok", "service": "humanizer", "version": "0.1.0"}


def test_command_analyze_returns_normalized_result() -> None:
    commands = build_commands()

    payload = commands.analyze(AnalyzeRequest(text="Sample", profile="ai_detection"))

    assert payload["status"] == "success"
    assert payload["result"]["profile"] == "ai_detection"
    assert set(payload["result"]["selected_providers"]) == {
        "anthropic",
        "gemini",
        "openai",
        "perplexity",
    }
    assert "consensus" in payload["result"]
    assert "worst_case" in payload["result"]
    assert "summary" in payload["result"]
    assert len(payload["result"]["summary"]["humanization_changes"]) >= 1


def test_command_analyze_batch_returns_per_item_results() -> None:
    commands = build_commands()

    payload = commands.analyze_batch(
        BatchAnalyzeRequest(
            items=[
                AnalyzeRequest(text="Sample", profile="ai_detection"),
                AnalyzeRequest(text="Sample", profile="bad_profile"),
            ]
        )
    )

    assert payload["results"][0]["status"] == "success"
    assert payload["results"][1]["status"] == "error"


def test_command_humanize_rewrites_and_returns_iteration_history() -> None:
    commands = build_commands()

    payload = commands.humanize(
        HumanizeRequest(
            text="Furthermore, individuals utilize numerous repetitive phrases in order to communicate.",
            threshold=0.40,
            max_iterations=2,
        )
    )

    assert payload["status"] == "success"
    assert payload["result"]["rewritten_text"]
    assert len(payload["result"]["iterations"]) >= 1
    assert "final_analysis" in payload["result"]
    assert payload["result"]["humanizer_provider"] == "openai"
    assert payload["result"]["humanizer_model"] == "gpt-5-mini"


def test_command_provider_status_returns_provider_entries() -> None:
    commands = build_commands()

    payload = commands.provider_status()

    assert payload["status"] == "success"
    assert {item["name"] for item in payload["providers"]} == {
        "anthropic",
        "gemini",
        "grok",
        "openai",
        "perplexity",
    }
    assert all("detail" in item for item in payload["providers"])
