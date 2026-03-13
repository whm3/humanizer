from fastapi.testclient import TestClient

from tests.conftest import create_test_client


def test_health_endpoint_returns_service_metadata() -> None:
    client = create_test_client()

    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "humanizer"


def test_version_endpoint_returns_version_metadata() -> None:
    client = create_test_client()

    response = client.get("/v1/version")

    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"


def test_providers_endpoint_lists_supported_providers() -> None:
    client = create_test_client()

    response = client.get("/v1/providers")

    assert response.status_code == 200
    assert {item["name"] for item in response.json()["providers"]} == {"openai", "perplexity"}


def test_analyze_endpoint_returns_normalized_result() -> None:
    client = create_test_client()

    response = client.post(
        "/v1/analyze",
        json={"text": "This is a sample sentence for analysis.", "profile": "ai_detection"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "success"
    assert payload["result"]["profile"] == "ai_detection"
    assert payload["result"]["provider"] == "openai"
    assert payload["result"]["request_id"].startswith("req_")


def test_analyze_endpoint_rejects_unsupported_profile() -> None:
    client = create_test_client()

    response = client.post(
        "/v1/analyze",
        json={"text": "This is a sample sentence for analysis.", "profile": "not_real"},
    )

    assert response.status_code == 400
    assert "unsupported profile" in response.json()["detail"]


def test_batch_endpoint_returns_partial_failures() -> None:
    client = create_test_client()

    response = client.post(
        "/v1/analyze/batch",
        json={
            "items": [
                {"text": "Normal text.", "profile": "ai_detection"},
                {"text": "Bad profile sample.", "profile": "unknown"},
            ]
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["results"][0]["status"] == "success"
    assert payload["results"][1]["status"] == "error"


def test_batch_endpoint_rejects_oversized_batch() -> None:
    client = create_test_client()

    response = client.post(
        "/v1/analyze/batch",
        json={
            "items": [
                {"text": f"Text {index}", "profile": "ai_detection"}
                for index in range(21)
            ]
        },
    )

    assert response.status_code == 400
    assert "batch exceeds configured limit" in response.json()["detail"]
