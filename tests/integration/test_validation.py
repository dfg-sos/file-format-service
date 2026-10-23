"""Integration tests for the upload endpoints ``/validate/structural`` and ``/validate/full``."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from ..conftest import DATA
from .conftest import GEOJSON_FORM, SHAPEFILE_FORM, upload

SAMPLE = DATA / "sample.geojson"
SAMPLE_POINT = DATA / "sample_point.geojson"


def _validate(client: TestClient, path: Path = SAMPLE, mode: str = "structural", **fields: object) -> Response:
    """Upload ``path`` as GeoJSON; ``fields`` override the form, ``None`` drops a field."""
    form = {k: v for k, v in (GEOJSON_FORM | fields).items() if v is not None}
    return upload(client, mode, form, path)


def _messages(response: Response, kind: str) -> list[str]:
    """Messages of one event kind (``errors``, ``warnings``, ``infos``)."""
    return [event["message"] for event in response.json()[kind]]


class TestRequestErrors:
    def test_missing_file(self, client: TestClient) -> None:
        response = client.post("/api/v1/validate/structural", data=GEOJSON_FORM)
        assert response.status_code == 422

    @pytest.mark.parametrize("mode", ["thorough", "BASIC"])
    def test_unknown_mode(self, client: TestClient, mode: str) -> None:
        assert _validate(client, mode=mode).status_code == 404

    @pytest.mark.parametrize(
        ("fields", "status_code"),
        [
            pytest.param({"format_identifier": "format_9999"}, 400, id="unmapped-format"),
            pytest.param({"ontology_namespace": None}, 422, id="missing-namespace"),
            pytest.param({"format_identifier": None}, 422, id="missing-format"),
        ],
    )
    def test_rejected(self, client: TestClient, fields: dict, status_code: int) -> None:
        assert _validate(client, **fields).status_code == status_code


class TestOutcome:
    def test_success(self, client: TestClient) -> None:
        response = _validate(client)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert {"errors", "warnings", "infos"} <= data.keys()

    def test_wrong_format_fails(self, client: TestClient) -> None:
        response = _validate(client, format_identifier="GeoPackage")
        assert response.json()["status"] == "FAILURE"
        assert _messages(response, "errors") != []

    def test_format_without_validator_is_uncertain(self, client: TestClient) -> None:
        """EsriJSON is mapped, but the validator has no implementation for it."""
        response = _validate(client, format_identifier="EsriJSON")
        assert response.json()["status"] == "UNCERTAIN"
        assert "not supported" in _messages(response, "warnings")[0]

    @pytest.mark.parametrize("mode", ["structural", "full"])
    def test_modes(self, client: TestClient, mode: str) -> None:
        """Both upload modes succeed for a valid file."""
        assert _validate(client, mode=mode).json()["status"] == "SUCCESS"

    def test_unknown_namespace_falls_back_to_all_mappings(self, client: TestClient) -> None:
        """Pins the FormatTranslator fallback: a format known under another
        ontology still resolves instead of yielding 400. Not an endorsement."""
        response = _validate(client, ontology_namespace="http://unknown-ontology.org")
        assert response.json()["status"] == "SUCCESS"

    def test_filename_without_extension_fails(self, client: TestClient, tmp_path: Path) -> None:
        """The upload is stored without a suffix, which fails the extension check.
        (An empty filename cannot be tested: it is not sent as a file part.)"""
        noext = tmp_path / "noext"
        noext.write_bytes(SAMPLE.read_bytes())
        response = _validate(client, noext)
        assert response.json()["status"] == "FAILURE"
        assert _messages(response, "errors") != []


class TestFullModeMetadata:
    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({}, id="omitted"),
            pytest.param({"expected_metadata": {}}, id="empty"),
            pytest.param({"expected_metadata": {"crs": "", "geometry_type": ""}}, id="blank"),
        ],
    )
    def test_checks_skipped_without_expected_values(self, client: TestClient, fields: dict) -> None:
        response = _validate(client, mode="full", **fields)
        assert response.json()["status"] == "SUCCESS"
        infos = _messages(response, "infos")
        assert any("skipping CRS validation" in m for m in infos)
        assert any("skipping geometry type validation" in m for m in infos)

    @pytest.mark.parametrize(
        ("path", "fields"),
        [
            # fiona reports EPSG:4326 for plain GeoJSON, even without features.
            pytest.param(SAMPLE, {"expected_metadata": {"crs": "EPSG:4326"}}, id="crs"),
            pytest.param(SAMPLE_POINT, {"expected_metadata": {"geometry_type": "Point"}}, id="geometry"),
            pytest.param(
                SAMPLE_POINT, {"expected_metadata": {"geometry_type": "point"}}, id="geometry-case-insensitive"
            ),
        ],
    )
    def test_match_succeeds(self, client: TestClient, path: Path, fields: dict) -> None:
        response = _validate(client, path, mode="full", **fields)
        assert response.json()["status"] == "SUCCESS"
        assert _messages(response, "errors") == []

    @pytest.mark.parametrize(
        ("path", "fields", "message"),
        [
            pytest.param(SAMPLE, {"expected_metadata": {"crs": "EPSG:3857"}}, "does not match expected CRS", id="crs"),
            # Not MultiPoint: the validator treats Point and MultiPoint as compatible.
            pytest.param(
                SAMPLE_POINT,
                {"expected_metadata": {"geometry_type": "Polygon"}},
                "do not include expected type",
                id="geometry",
            ),
        ],
    )
    def test_mismatch_fails(self, client: TestClient, path: Path, fields: dict, message: str) -> None:
        response = _validate(client, path, mode="full", **fields)
        assert response.json()["status"] == "FAILURE"
        assert any(message in m for m in _messages(response, "errors"))

    @pytest.mark.parametrize(
        ("path", "fields"),
        [
            pytest.param(SAMPLE, {"expected_metadata": {"crs": "totally-bogus-crs-string"}}, id="crs"),
            pytest.param(SAMPLE_POINT, {"expected_metadata": {"geometry_type": "NotAGeometry"}}, id="geometry"),
        ],
    )
    def test_unparseable_value_is_uncertain(self, client: TestClient, path: Path, fields: dict) -> None:
        """The request cannot be built: reported as UNCERTAIN, not a crash, 400 or skipped check."""
        response = _validate(client, path, mode="full", **fields)
        assert response.json()["status"] == "UNCERTAIN"
        assert any("ValidationRequest could not be built" in m for m in _messages(response, "warnings"))

    @pytest.mark.parametrize(
        ("format_identifier", "metadata"),
        [
            pytest.param("GeoJSON", {"encoding": "utf-8"}, id="unknown-key"),
            # Raster validators take no geometry type.
            pytest.param("GeoTIFF", {"geometry_type": "Point"}, id="key-of-other-validator"),
            # The format has no validator, so no metadata can be checked.
            pytest.param("EsriJSON", {"crs": "EPSG:4326"}, id="format-without-validator"),
        ],
    )
    def test_unsupported_key_rejected(self, client: TestClient, format_identifier: str, metadata: dict) -> None:
        response = _validate(client, mode="full", format_identifier=format_identifier, expected_metadata=metadata)
        assert response.status_code == 400
        assert "Unsupported expected_metadata key" in response.json()["detail"]

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("{not json", id="malformed"),
            pytest.param('["crs"]', id="not-an-object"),
            pytest.param('{"crs": 4326}', id="non-string-value"),
        ],
    )
    def test_invalid_metadata_field(self, client: TestClient, raw: str) -> None:
        assert _validate(client, mode="full", expected_metadata=raw).status_code == 422

    def test_structural_ignores_metadata_field(self, client: TestClient) -> None:
        """Metadata belongs to full validation only; the structural form has no such field."""
        response = _validate(client, expected_metadata={"encoding": "utf-8"})
        assert response.json()["status"] == "SUCCESS"


class TestMultiFileValidation:
    FORM = SHAPEFILE_FORM

    @pytest.mark.parametrize(
        ("extensions", "status"),
        [
            pytest.param([".shx", ".dbf", ".prj"], "SUCCESS", id="complete"),
            pytest.param([".shx"], "FAILURE", id="incomplete"),
        ],
    )
    def test_secondary_files(
        self, client: TestClient, sample_shapefile: Path, extensions: list[str], status: str
    ) -> None:
        secondary = [sample_shapefile.with_suffix(ext) for ext in extensions]
        response = upload(client, "structural", self.FORM, sample_shapefile, secondary)
        assert response.status_code == 200
        assert response.json()["status"] == status
        if status == "FAILURE":
            assert any("Missing required secondary files" in m for m in _messages(response, "errors"))

    def test_duplicate_file_names_rejected(self, client: TestClient, sample_shapefile: Path) -> None:
        with sample_shapefile.open("rb") as f:
            response = client.post(
                "/api/v1/validate/structural",
                files=[
                    ("file", (sample_shapefile.name, f, "application/octet-stream")),
                    ("secondary_files", (sample_shapefile.name, b"x", "application/octet-stream")),
                ],
                data=self.FORM,
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
