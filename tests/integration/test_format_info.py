"""Integration tests for the ``/format-info`` endpoint."""

from pathlib import Path


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

    def test_format_info_invalid_local_schema(self, client, sample_geojson: Path):
        """A local file:// schema URL that isn't valid RDF yields 400, not a crash."""
        payload = {
            "ontology_schema_url": sample_geojson.as_uri(),
            "format_identifier": "format_4119",
        }
        response = client.post("/api/v1/format-info", json=payload)
        assert response.status_code == 400

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
