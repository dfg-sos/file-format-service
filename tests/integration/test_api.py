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


@pytest.fixture
def ontology_file() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "edamontology_adapted.org.owl"


@pytest.fixture
def sample_geojson() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "sample.geojson"


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestCompatibilityEndpoint:
    def test_compatibility_same_format(self, client: TestClient, ontology_file: Path) -> None:
        """Identity check: a format is always compatible with itself."""
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

    def test_compatibility_subclass(
        self, client: TestClient, ontology_file: Path
    ) -> None:
        """Shapefile (format_4119) is a subclass of vector (format_4126)."""
        payload = {
            "expected_format": "format_4126",
            "actual_format": "format_4119",
            "ontology_schema_url": ontology_file.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["compatible"] is True
        assert "format_4119" in data["message"]
        assert "format_4126" in data["message"]

    def test_compatibility_incompatible_formats(
        self, client: TestClient, ontology_file: Path
    ) -> None:
        """GeoTIFF (format_4109) is not compatible with Shapefile (format_4119)."""
        payload = {
            "expected_format": "format_4119",
            "actual_format": "format_4109",
            "ontology_schema_url": ontology_file.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["compatible"] is False
        assert "not" in data["message"].lower()

    def test_compatibility_missing_schema_url(
        self, client: TestClient
    ) -> None:
        """A request without ontology_schema_url yields 422."""
        payload = {
            "expected_format": "format_4119",
            "actual_format": "format_4119",
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 422

    def test_compatibility_invalid_schema_url(
        self, client: TestClient
    ) -> None:
        """An unreachable schema URL yields a 4xx error."""
        payload = {
            "expected_format": "format_4119",
            "actual_format": "format_4119",
            "ontology_schema_url": "http://localhost:65432/nonexistent.owl",
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 502


class TestValidationEndpoint:
    def test_validate_success(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """Upload a valid GeoJSON and validate it against the geojson format."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "full",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert "errors" in data
        assert "warnings" in data
        assert "infos" in data

    def test_validate_failure(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """Upload a valid GeoJSON and validate it against the geojson format."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4107",
                    "mode": "basic",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "FAILURE"
        assert data["errors"] is not None
        assert data["errors"] != []

    def test_validate_missing_file(self, client: TestClient) -> None:
        """A request without a file yields 422."""
        response = client.post(
            "/api/v1/validate",
            data={
                "ontology_namespace": "http://edamontology.org",
                "format_identifier": "format_4106",
                "mode": "basic",
            },
        )
        assert response.status_code == 422

    def test_validate_invalid_mode(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """An unknown validation mode yields 400."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "invalid_mode",
                },
            )
        assert response.status_code == 400

    def test_validate_unknown_format(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """A format identifier not present in the mappings yields 400."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_9999",
                    "mode": "basic",
                },
            )
        assert response.status_code == 400


class TestFormatInfoEndpoint:
    def test_format_info_shapefile(self, client, ontology_file):
        payload = {
            "ontology_schema_url": str(ontology_file.as_uri()),
            "format_identifier": "format_4119",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["format_uri"] == "http://edamontology.org/format_4119"
        assert data["label"] == "Shapefile"
        assert "composite format" in (data["comment"] or "").lower()
        # Shapefile is a subclass of format_2333, format_4126, format_4127
        assert any("format_2333" in p for p in data["parents"])
        assert len(data["file_extensions"]) >= 2  # shp, shx, dbf
        assert data["media_type"] is not None

    def test_format_info_with_children(self, client, ontology_file):
        # format_4126 (Vector GIS data) should have format_4119 (Shapefile) as child
        payload = {
            "ontology_schema_url": str(ontology_file.as_uri()),
            "format_identifier": "format_4126",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert any("format_4119" in c for c in data["children"])

    def test_format_info_missing_schema_url(self, client):
        payload = {"format_identifier": "format_4119"}
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 422

    def test_format_info_invalid_schema_url(self, client):
        payload = {
            "ontology_schema_url": "http://localhost:59999/nonexistent.owl",
            "format_identifier": "format_4119",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 502

    def test_format_info_unknown_format(self, client, ontology_file):
        # Unknown format should return empty metadata, not crash
        payload = {
            "ontology_schema_url": str(ontology_file.as_uri()),
            "format_identifier": "format_99999",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["format_uri"] == "http://edamontology.org/format_99999"
        assert data["label"] is None
        assert data["parents"] == []
        assert data["children"] == []
