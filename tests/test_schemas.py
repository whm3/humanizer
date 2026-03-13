import pytest
from pydantic import ValidationError

from humanizer.api.schemas import AnalyzeRequest, BatchAnalyzeRequest


def test_analyze_request_strips_text() -> None:
    request = AnalyzeRequest(text="  hello world  ", profile="ai_detection")

    assert request.text == "hello world"


def test_analyze_request_rejects_blank_text() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest(text="   ", profile="ai_detection")


def test_batch_request_requires_at_least_one_item() -> None:
    with pytest.raises(ValidationError):
        BatchAnalyzeRequest(items=[])
