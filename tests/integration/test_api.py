"""Integration tests for the FastAPI application.

These tests start the full app and exercise the HTTP endpoints.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestCompatibilityEndpoint:
    def test_compatibility_same_format(self, client: TestClient) -> None:
        ontology_file = Path(__file__).parent.parent / "fixtures" / "edamontology_adapted.org.owl"
        payload = {
            "expected_format": "format_4119",
            "actual_format": "format_4119",
            "ontology_schema_url": ontology_file.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["compatible"] is True
        assert "format_4119" in data["message"]
