import json

from humanizer.core.token_usage import TokenUsageLogger, extract_token_usage


def test_extract_token_usage_for_openai() -> None:
    record = extract_token_usage(
        "openai",
        "gpt-5-mini",
        "analyze",
        {"usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}},
    )

    assert record is not None
    assert record.input_tokens == 11
    assert record.output_tokens == 7
    assert record.total_tokens == 18


def test_extract_token_usage_for_gemini() -> None:
    record = extract_token_usage(
        "gemini",
        "gemini-2.5-flash",
        "rewrite",
        {"usageMetadata": {"promptTokenCount": 13, "candidatesTokenCount": 5, "totalTokenCount": 18}},
    )

    assert record is not None
    assert record.input_tokens == 13
    assert record.output_tokens == 5
    assert record.total_tokens == 18


def test_extract_token_usage_for_perplexity() -> None:
    record = extract_token_usage(
        "perplexity",
        "sonar",
        "review",
        {"usage": {"prompt_tokens": 17, "completion_tokens": 3, "total_tokens": 20}},
    )

    assert record is not None
    assert record.input_tokens == 17
    assert record.output_tokens == 3
    assert record.total_tokens == 20


def test_extract_token_usage_for_anthropic() -> None:
    record = extract_token_usage(
        "anthropic",
        "claude-sonnet-4-5",
        "analyze",
        {"usage": {"input_tokens": 21, "output_tokens": 6}},
    )

    assert record is not None
    assert record.input_tokens == 21
    assert record.output_tokens == 6
    assert record.total_tokens == 27


def test_token_usage_logger_writes_jsonl(tmp_path) -> None:
    log_path = tmp_path / "token-usage.jsonl"
    logger = TokenUsageLogger(str(log_path))

    logger.log_response(
        provider="openai",
        model="gpt-5-mini",
        operation="openai request",
        response_payload={"usage": {"input_tokens": 9, "output_tokens": 4, "total_tokens": 13}},
    )

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-5-mini"
    assert payload["operation"] == "openai request"
    assert payload["input_tokens"] == 9
    assert payload["output_tokens"] == 4
    assert payload["total_tokens"] == 13
