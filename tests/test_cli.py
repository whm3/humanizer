import json

from humanizer.cli import main


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
    assert {item["name"] for item in payload["providers"]} == {"openai", "perplexity"}


def test_cli_analyze_outputs_normalized_result(capsys) -> None:
    exit_code = main(["analyze", "--text", "Sample input text", "--profile", "ai_detection"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["result"]["profile"] == "ai_detection"
    assert payload["result"]["provider"] == "openai"
