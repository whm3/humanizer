from fastapi.testclient import TestClient

from humanizer.api.app import create_app


def create_test_client() -> TestClient:
    return TestClient(create_app())
