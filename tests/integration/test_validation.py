"""Integration tests for the ``/validate`` endpoint."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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
        """A format that is mapped but has no registered validator (esrijson)
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

    def test_validate_full_mode_invalid_geometry_type_uncertain(
        self, client: TestClient, sample_geojson_with_point: Path
    ) -> None:
        """An unknown expected_geometry_type is reported as UNCERTAIN, like an
        invalid CRS, instead of silently skipping the geometry check."""
        with sample_geojson_with_point.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files={"file": ("sample_point.geojson", f, "application/geo+json")},
                data={
                    "ontology_namespace": "http://edamontology.org",
                    "format_identifier": "format_4106",
                    "mode": "full",
                    "expected_geometry_type": "NotAGeometry",
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


class TestMultiFileValidation:
    _FORM = {
        "ontology_namespace": "http://edamontology.org",
        "format_identifier": "format_4119",
        "mode": "structural",
    }

    def _post(self, client: TestClient, shp: Path, extensions: list[str]):
        with shp.open("rb") as primary:
            files: list = [("file", (shp.name, primary, "application/octet-stream"))]
            handles = []
            for ext in extensions:
                h = shp.with_suffix(ext).open("rb")
                handles.append(h)
                files.append(("secondary_files", (shp.with_suffix(ext).name, h, "application/octet-stream")))
            try:
                return client.post("/api/v1/validate", files=files, data=self._FORM)
            finally:
                for h in handles:
                    h.close()

    def test_shapefile_with_secondary_files(self, client: TestClient, sample_shapefile: Path) -> None:
        response = self._post(client, sample_shapefile, [".shx", ".dbf", ".prj"])
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"

    def test_shapefile_missing_secondary_files(self, client: TestClient, sample_shapefile: Path) -> None:
        response = self._post(client, sample_shapefile, [".shx"])
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "FAILURE"
        assert any("Missing required secondary files" in e["message"] for e in data["errors"])

    def test_duplicate_file_names_rejected(self, client: TestClient, sample_shapefile: Path) -> None:
        with sample_shapefile.open("rb") as f:
            response = client.post(
                "/api/v1/validate",
                files=[
                    ("file", (sample_shapefile.name, f, "application/octet-stream")),
                    ("secondary_files", (sample_shapefile.name, b"x", "application/octet-stream")),
                ],
                data=self._FORM,
            )
        assert response.status_code == 400


class TestSafeFilename:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("roads.shp", "roads.shp"),
            ("../../etc/passwd", "passwd"),
            ("/abs/path/roads.shp", "roads.shp"),
            ("..\\..\\evil.dll", "evil.dll"),
            ("C:\\Users\\me\\roads.shp", "roads.shp"),
            ("a/b\\c.dbf", "c.dbf"),
            ("dir/", "dir"),
            ("..", "fallback"),
            (".", "fallback"),
            ("", "fallback"),
            (None, "fallback"),
        ],
    )
    def test_safe_filename(self, raw: str | None, expected: str) -> None:
        from io import BytesIO

        from fastapi import UploadFile

        from api.routers.validation import _safe_filename

        upload = UploadFile(BytesIO(b""), filename=raw)
        assert _safe_filename(upload, "fallback") == expected
