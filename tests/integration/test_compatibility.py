"""Integration tests for the ``/compatibility`` endpoint."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class TestCompatibilityEndpoint:
    def test_compatibility_same_format(self, client: TestClient, ontology_file: Path) -> None:
        """Identity check: a format is always compatible with itself."""
        payload = {
            "expected_format": "Shapefile",
            "actual_format": "Shapefile",
            "ontology_schema_url": ontology_file.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["compatible"] is True
        assert "Shapefile" in data["message"]

    def test_compatibility_subclass(
        self, client: TestClient, ontology_file: Path
    ) -> None:
        """Shapefile is a subclass of Vector."""
        payload = {
            "expected_format": "Vector",
            "actual_format": "Shapefile",
            "ontology_schema_url": ontology_file.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["compatible"] is True
        assert "Shapefile" in data["message"]
        assert "Vector" in data["message"]

    def test_compatibility_incompatible_formats(
        self, client: TestClient, ontology_file: Path
    ) -> None:
        """GeoTIFF is not compatible with Shapefile."""
        payload = {
            "expected_format": "Shapefile",
            "actual_format": "GeoTIFF",
            "ontology_schema_url": ontology_file.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["compatible"] is False
        assert "not" in data["message"].lower()

    @pytest.mark.parametrize(
        ("expected", "actual", "compatible"),
        [
            ("GeoTIFF", "COG", True),
            ("Raster", "COG", True),
            ("Vector", "Shapefile", True),
            ("Raster", "Shapefile", False),
        ],
    )
    def test_compatibility_hierarchy(
        self, client: TestClient, ontology_file: Path, expected: str, actual: str, compatible: bool
    ) -> None:
        payload = {
            "expected_format": expected,
            "actual_format": actual,
            "ontology_schema_url": ontology_file.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 200
        assert response.json()["compatible"] is compatible

    def test_compatibility_missing_schema_url(
        self, client: TestClient
    ) -> None:
        """A request without ontology_schema_url yields 422."""
        payload = {
            "expected_format": "Shapefile",
            "actual_format": "Shapefile",
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 422

    def test_compatibility_invalid_schema_url(
        self, client: TestClient
    ) -> None:
        """An unreachable schema URL yields a 4xx error."""
        payload = {
            "expected_format": "Shapefile",
            "actual_format": "Shapefile",
            "ontology_schema_url": "http://localhost:65432/nonexistent.owl",
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 502

    def test_compatibility_invalid_local_schema(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """A local file:// schema URL that isn't valid RDF yields 400, not a crash."""
        payload = {
            "expected_format": "Shapefile",
            "actual_format": "Shapefile",
            "ontology_schema_url": sample_geojson.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 400

    def test_compatibility_missing_local_schema(self, client: TestClient, tmp_path: Path) -> None:
        """A file:// schema URL pointing to no file yields 404."""
        payload = {
            "expected_format": "Shapefile",
            "actual_format": "Shapefile",
            "ontology_schema_url": (tmp_path / "missing.owl").as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 404
        assert "missing.owl" in response.json()["detail"]

    def test_compatibility_unknown_actual_format(
        self, client: TestClient, ontology_file: Path
    ) -> None:
        """An undefined actual format yields 422 listing only that format."""
        payload = {
            "expected_format": "Vector",
            "actual_format": "format_99999",
            "ontology_schema_url": ontology_file.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert ontology_file.as_uri() in detail["message"]
        assert detail["unknown_formats"] == ["https://w3id.org/sos/eo-formats/format_99999"]

    def test_compatibility_unknown_expected_format(
        self, client: TestClient, ontology_file: Path
    ) -> None:
        """An undefined expected format yields 422 listing only that format."""
        payload = {
            "expected_format": "format_99998",
            "actual_format": "Shapefile",
            "ontology_schema_url": ontology_file.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 422
        assert response.json()["detail"]["unknown_formats"] == [
            "https://w3id.org/sos/eo-formats/format_99998"
        ]

    def test_compatibility_both_formats_unknown(
        self, client: TestClient, ontology_file: Path
    ) -> None:
        """When both formats are undefined, both are listed."""
        payload = {
            "expected_format": "format_99998",
            "actual_format": "format_99999",
            "ontology_schema_url": ontology_file.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 422
        assert response.json()["detail"]["unknown_formats"] == [
            "https://w3id.org/sos/eo-formats/format_99998",
            "https://w3id.org/sos/eo-formats/format_99999",
        ]
