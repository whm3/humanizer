import json
from pathlib import Path

from humanizer.cli import main
from humanizer.providers.base import ProviderResult
from humanizer.providers.openai_adapter import OpenAIAdapter


def test_cli_health_outputs_json(capsys) -> None:
    exit_code = main(["health"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "ok"


def test_cli_version_outputs_json(capsys) -> None:
    exit_code = main(["version"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["version"] == "0.1.0"


def test_cli_providers_list_outputs_known_providers(capsys) -> None:
    exit_code = main(["providers", "list"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert {item["name"] for item in payload["providers"]} == {
        "anthropic",
        "gemini",
        "grok",
        "openai",
        "perplexity",
    }


def test_cli_providers_check_outputs_provider_status(capsys) -> None:
    exit_code = main(["providers", "check"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "success"
    assert {item["name"] for item in payload["providers"]} == {
        "anthropic",
        "gemini",
        "grok",
        "openai",
        "perplexity",
    }


def test_cli_providers_check_can_ignore_environment_keys(capsys) -> None:
    exit_code = main(["providers", "--ignore-env-keys", "check"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "success"
    assert payload["providers"] == []


def test_cli_analyze_outputs_normalized_result(capsys) -> None:
    exit_code = main(["analyze", "--text", "Sample input text", "--profile", "ai_detection"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
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


def test_cli_analyze_accepts_request_scoped_api_keys(monkeypatch, capsys) -> None:
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

    exit_code = main(
        [
            "analyze",
            "--text",
            "Sample input text",
            "--profile",
            "ai_detection",
            "--ignore-env-keys",
            "--openai-api-key",
            "request-openai-key",
            "--provider",
            "openai",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["result"]["selected_providers"] == ["openai"]


def test_cli_analyze_batch_outputs_mixed_results(tmp_path: Path, capsys) -> None:
    payload_path = tmp_path / "batch.json"
    payload_path.write_text(
        json.dumps(
            {
                "items": [
                    {"text": "Sample input text", "profile": "ai_detection"},
                    {"text": "Bad profile text", "profile": "not_real"},
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["analyze-batch", "--file", str(payload_path)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["results"][0]["status"] == "success"
    assert payload["results"][1]["status"] == "error"


def test_cli_humanize_outputs_rewrite_and_final_analysis(capsys) -> None:
    exit_code = main(
        [
            "humanize",
            "--text",
            "Furthermore, individuals utilize numerous repetitive phrases in order to communicate.",
            "--threshold",
            "0.40",
            "--max-iterations",
            "2",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["result"]["rewritten_text"]
    assert len(payload["result"]["iterations"]) >= 1
    assert "final_analysis" in payload["result"]
    assert payload["result"]["humanizer_provider"] == "openai"
    assert payload["result"]["humanizer_model"] == "gpt-5-mini"


def test_cli_humanize_can_write_debug_output_file(tmp_path: Path, capsys) -> None:
    debug_path = tmp_path / "debug" / "humanize.json"

    exit_code = main(
        [
            "humanize",
            "--text",
            "Furthermore, individuals utilize numerous repetitive phrases in order to communicate.",
            "--threshold",
            "0.40",
            "--max-iterations",
            "1",
            "--debug-output-file",
            str(debug_path),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    written = json.loads(debug_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "success"
    assert written["status"] == "success"


def test_cli_analyze_code_marks_content_type(capsys) -> None:
    exit_code = main(
        [
            "analyze",
            "--text",
            "import os\n\ndef main():\n    return os.getcwd()\n",
            "--profile",
            "ai_detection",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["result"]["content_type"] == "code"
