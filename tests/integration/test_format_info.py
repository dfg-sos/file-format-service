"""Integration tests for the ``/format-info`` endpoint."""

from pathlib import Path

from ..conftest import EXAMPLE_NAMESPACE


class TestFormatInfoEndpoint:
    def test_format_info_shapefile(self, client, ontology_file):
        payload = {
            "ontology_schema_url": str(ontology_file.as_uri()),
            "format_identifier": "Shapefile",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["format_uri"] == EXAMPLE_NAMESPACE + "Shapefile"
        assert data["label"] == "Shapefile"
        assert "composite format" in (data["comment"] or "").lower()
        assert data["parents"] == [EXAMPLE_NAMESPACE + "Vector"]
        annotations = data["annotations"]
        assert annotations[EXAMPLE_NAMESPACE + "fileExtension"] == ["dbf", "shp", "shx"]
        assert "http://www.w3.org/2000/01/rdf-schema#subClassOf" not in annotations

    def test_format_info_with_children(self, client, ontology_file):
        payload = {
            "ontology_schema_url": str(ontology_file.as_uri()),
            "format_identifier": "Vector",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert EXAMPLE_NAMESPACE + "Shapefile" in data["children"]

    def test_format_info_missing_schema_url(self, client):
        payload = {"format_identifier": "Shapefile"}
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 422

    def test_format_info_invalid_schema_url(self, client):
        payload = {
            "ontology_schema_url": "http://localhost:59999/nonexistent.owl",
            "format_identifier": "Shapefile",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 502

    def test_format_info_invalid_local_schema(self, client, sample_geojson: Path):
        """A local file:// schema URL that isn't valid RDF yields 400, not a crash."""
        payload = {
            "ontology_schema_url": sample_geojson.as_uri(),
            "format_identifier": "Shapefile",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 400

    def test_format_info_missing_local_schema(self, client, tmp_path: Path):
        """A file:// schema URL pointing to no file yields 404."""
        payload = {
            "ontology_schema_url": (tmp_path / "missing.owl").as_uri(),
            "format_identifier": "Shapefile",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 404
        assert "missing.owl" in response.json()["detail"]

    def test_format_info_unknown_format(self, client, ontology_file):
        """A format not defined in the ontology yields 404 with its expanded IRI."""
        payload = {
            "ontology_schema_url": str(ontology_file.as_uri()),
            "format_identifier": "format_99999",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert ontology_file.as_uri() in detail["message"]
        assert detail["unknown_formats"] == ["https://example.org/formats/format_99999"]
