import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_returns_service_metadata(client: AsyncClient) -> None:
    response = await client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "humanizer"


@pytest.mark.asyncio
async def test_version_endpoint_returns_version_metadata(client: AsyncClient) -> None:
    response = await client.get("/v1/version")

    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_providers_endpoint_lists_supported_providers(client: AsyncClient) -> None:
    response = await client.get("/v1/providers")

    assert response.status_code == 200
    assert {item["name"] for item in response.json()["providers"]} == {
        "anthropic",
        "deepseek",
        "gemini",
        "grok",
        "openai",
        "perplexity",
    }


@pytest.mark.asyncio
async def test_analyze_endpoint_returns_normalized_result(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/analyze",
        json={"text": "This is a sample sentence for analysis.", "profile": "ai_detection"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "success"
    assert payload["result"]["profile"] == "ai_detection"
    assert set(payload["result"]["selected_providers"]) == {
        "anthropic",
        "deepseek",
        "gemini",
        "grok",
        "openai",
        "perplexity",
    }
    assert payload["result"]["consensus"]["providers_considered"]
    assert payload["result"]["request_id"].startswith("req_")


@pytest.mark.asyncio
async def test_analyze_endpoint_rejects_unsupported_profile(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/analyze",
        json={"text": "This is a sample sentence for analysis.", "profile": "not_real"},
    )

    assert response.status_code == 400
    assert "unsupported profile" in response.json()["detail"]


@pytest.mark.asyncio
async def test_batch_endpoint_returns_partial_failures(client: AsyncClient) -> None:
    response = await client.post(
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


@pytest.mark.asyncio
async def test_batch_endpoint_rejects_oversized_batch(client: AsyncClient) -> None:
    response = await client.post(
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


@pytest.mark.asyncio
async def test_humanize_endpoint_returns_iterations(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/humanize",
        json={
            "text": "Furthermore, individuals utilize numerous repetitive phrases in order to communicate.",
            "threshold": 0.40,
            "max_iterations": 2,
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "success"
    assert payload["result"]["iterations"]
    assert payload["result"]["final_analysis"]["profile"] == "ai_detection"
