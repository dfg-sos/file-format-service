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


@pytest.fixture
def sample_geojson_with_point() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "sample_point.geojson"


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

    def test_compatibility_invalid_local_schema(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """A local file:// schema URL that isn't valid RDF yields 400, not a crash."""
        payload = {
            "expected_format": "format_4119",
            "actual_format": "format_4119",
            "ontology_schema_url": sample_geojson.as_uri(),
        }
        response = client.post("/api/v1/compatibility", json=payload)
        assert response.status_code == 400


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

    def test_validate_uncertain_unsupported_format(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """A format that is mapped but has no registered validator (osm_json)
        yields an UNCERTAIN status rather than SUCCESS/FAILURE."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4105",
                    "mode": "basic",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "UNCERTAIN"
        assert data["warnings"] != []
        assert "not supported" in data["warnings"][0]["message"]

    def test_validate_structural_mode(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """Structural mode (extension + existence checks) succeeds for a valid file."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "structural",
                },
            )
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"

    def test_validate_full_mode_skips_metadata_checks_without_expected_values(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """FULL mode enables metadata validation (CRS, geometry type) via the
        EOMetadata sidecar, but when the expected_crs / expected_geometry_type
        fields are omitted those checks are skipped with informational
        messages rather than failing."""
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
        assert data["errors"] == []
        info_messages = [info["message"] for info in data["infos"]]
        assert any("skipping CRS validation" in message for message in info_messages)
        assert any(
            "skipping geometry type validation" in message for message in info_messages
        )

    def test_validate_full_mode_blank_expected_fields_skip(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """Explicitly blank expected_crs / expected_geometry_type fields are
        treated the same as omitted ones (both are falsy to
        EOMetadata.from_strings), so metadata checks are still skipped."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "full",
                    "expected_crs": "",
                    "expected_geometry_type": "",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["errors"] == []
        info_messages = [info["message"] for info in data["infos"]]
        assert any("skipping CRS validation" in message for message in info_messages)
        assert any(
            "skipping geometry type validation" in message for message in info_messages
        )

    def test_validate_full_mode_crs_match_success(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """A matching expected_crs succeeds (fiona reports EPSG:4326 for a
        plain GeoJSON file by default, even with no features)."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "full",
                    "expected_crs": "EPSG:4326",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["errors"] == []

    def test_validate_full_mode_crs_mismatch_failure(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """A mismatching expected_crs fails validation."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "full",
                    "expected_crs": "EPSG:3857",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "FAILURE"
        assert any("does not match expected CRS" in e["message"] for e in data["errors"])

    def test_validate_full_mode_invalid_crs_uncertain(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """A syntactically invalid expected_crs cannot be parsed by
        EOMetadata.from_strings, so the request cannot be built and the
        endpoint reports UNCERTAIN rather than crashing or returning a 400."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "full",
                    "expected_crs": "totally-bogus-crs-string",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "UNCERTAIN"
        assert any(
            "ValidationRequest could not be built" in w["message"] for w in data["warnings"]
        )

    def test_validate_full_mode_geometry_type_match_success(
        self, client: TestClient, sample_geojson_with_point: Path
    ) -> None:
        """A matching expected_geometry_type succeeds."""
        with sample_geojson_with_point.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample_point.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "full",
                    "expected_geometry_type": "Point",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["errors"] == []

    def test_validate_full_mode_geometry_type_case_insensitive(
        self, client: TestClient, sample_geojson_with_point: Path
    ) -> None:
        """Geometry type names are matched case-insensitively."""
        with sample_geojson_with_point.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample_point.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "full",
                    "expected_geometry_type": "point",
                },
            )
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"

    def test_validate_full_mode_geometry_type_mismatch_failure(
        self, client: TestClient, sample_geojson_with_point: Path
    ) -> None:
        """A mismatching expected_geometry_type fails validation.

        Uses Polygon rather than MultiPoint: Point/MultiPoint are treated as
        compatible by the validator package, so that pair would wrongly
        succeed.
        """
        with sample_geojson_with_point.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample_point.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "full",
                    "expected_geometry_type": "Polygon",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "FAILURE"
        assert any(
            "do not include expected type" in e["message"] for e in data["errors"]
        )

    def test_validate_full_mode_unrecognized_geometry_type_treated_as_unset(
        self, client: TestClient, sample_geojson_with_point: Path
    ) -> None:
        """An unrecognized geometry type name isn't rejected: EOMetadata
        .from_strings silently maps it to None (same as not provided),
        rather than raising like an invalid CRS string does. This pins down
        that asymmetry rather than treating it as a bug to fix here."""
        with sample_geojson_with_point.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample_point.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "full",
                    "expected_geometry_type": "NotAShape",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        info_messages = [info["message"] for info in data["infos"]]
        assert any(
            "skipping geometry type validation" in message for message in info_messages
        )

    def test_validate_mode_case_insensitive(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """Mode strings are matched case-insensitively."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "BASIC",
                },
            )
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"

    def test_validate_namespace_mismatch_still_resolves(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """FormatTranslator falls back to searching all loaded ontologies, so
        a bogus namespace with a format known under a different ontology
        still resolves instead of yielding 400. This pins the current
        translator fallback behavior rather than endorsing it."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://unknown-ontology.org",
                    "format_identifier": "format_4106",
                    "mode": "basic",
                },
            )
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"

    def test_validate_missing_ontology_namespace(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """A request without ontology_namespace yields 422."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "format_identifier": "format_4106",
                    "mode": "basic",
                },
            )
        assert response.status_code == 422

    def test_validate_missing_format_identifier(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """A request without format_identifier yields 422."""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "mode": "basic",
                },
            )
        assert response.status_code == 422

    def test_validate_empty_filename(
        self, client: TestClient, sample_geojson: Path
    ) -> None:
        """A filename without an extension yields a suffix-less temp file,
        which fails the extension check instead of the format's expected
        extension. (An actually-empty filename can't be represented as a
        multipart file part: httpx/starlette parse it as a plain string
        field rather than an UploadFile.)"""
        with sample_geojson.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("noext", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "basic",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "FAILURE"
        assert data["errors"] != []


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
