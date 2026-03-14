import json
from pathlib import Path

from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import (
    AnalyzeRequest,
    ApiKeyOverrides,
    BatchAnalyzeRequest,
    HumanizeRequest,
    ProviderStatusRequest,
)
from humanizer.commands import CommandService
from humanizer.core.settings import Settings
from humanizer.providers.base import ProviderResult
from humanizer.providers.openai_adapter import OpenAIAdapter
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
    assert "usage_summary" in payload["result"]
    assert payload["result"]["usage_summary"]["run_id"].startswith("run_")
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
    assert payload["result"]["usage_summary"]["run_id"].startswith("run_")
    assert payload["result"]["humanizer_provider"] == "openai"
    assert payload["result"]["humanizer_model"] == "gpt-5-mini"


def test_command_humanize_can_write_debug_output_file(tmp_path: Path) -> None:
    commands = build_commands()
    debug_path = tmp_path / "debug" / "humanize.json"

    payload = commands.humanize(
        HumanizeRequest(
            text="Furthermore, individuals utilize numerous repetitive phrases in order to communicate.",
            threshold=0.40,
            max_iterations=1,
            debug_output_path=str(debug_path),
        )
    )

    written = json.loads(debug_path.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert written["status"] == "success"
    assert "iterations" in written["result"]


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


def test_command_provider_status_can_ignore_environment_keys() -> None:
    commands = build_commands()

    payload = commands.provider_status(ProviderStatusRequest(ignore_env_keys=True))

    assert payload["status"] == "success"
    assert payload["providers"] == []


def test_command_analyze_uses_request_scoped_keys_when_environment_is_ignored(
    monkeypatch,
) -> None:
    commands = build_commands()
    monkeypatch.setattr(
        OpenAIAdapter,
        "analyze",
        lambda self, request: ProviderResult(
            label="likely_human",
            score=0.2,
            confidence="medium",
            signals=["stubbed"],
            explanation="stubbed",
        ),
    )

    payload = commands.analyze(
        AnalyzeRequest(
            text="Sample",
            profile="ai_detection",
            ignore_env_keys=True,
            api_keys=ApiKeyOverrides(openai="request-openai-key"),
            provider="openai",
        )
    )

    assert payload["status"] == "success"
    assert payload["result"]["selected_providers"] == ["openai"]
