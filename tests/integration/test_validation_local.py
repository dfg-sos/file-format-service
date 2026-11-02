"""Integration tests for the ``/validate/{mode}/local`` endpoints."""

import re
from pathlib import Path, PurePosixPath

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_shared_path_resolver
from config import SharedDir
from service.shared_paths import SharedPathResolver

from ..conftest import DATA
from .conftest import GEOJSON_FORM, SHAPEFILE_FORM, create_test_app, upload


def _client_with_shared_dirs(*dirs: Path) -> TestClient:
    app = create_test_app()
    resolver = SharedPathResolver([SharedDir(PurePosixPath(d), d) for d in dirs])
    app.dependency_overrides[get_shared_path_resolver] = lambda: resolver
    return TestClient(app)


@pytest.fixture
def local_client(tmp_path: Path) -> TestClient:
    """Client whose service shares ``tests/fixtures/data`` and ``tmp_path``."""
    return _client_with_shared_dirs(DATA, tmp_path)


def _local(client: TestClient, mode: str, form: dict, primary: Path | str, secondary: list[Path] = []):
    body = {**form, "file_path": str(primary), "secondary_file_paths": [str(p) for p in secondary]}
    return client.post(f"/api/v1/validate/{mode}/local", json=body)


def _outcome(response) -> tuple:
    """Status and events, without timestamps."""
    data = response.json()
    events = [
        (kind, e["severity"], e["cause"], e["message"])
        for kind in ("errors", "warnings", "infos")
        for e in data[kind]
    ]
    return data["status"], sorted(events)


class TestSameResultAsUpload:
    @pytest.mark.parametrize(
        ("mode", "fixture", "metadata"),
        [
            ("metadata", "sample.geojson", {}),
            ("content", "sample.geojson", {}),
            ("metadata", "sample.geojson", {"crs": "EPSG:4326"}),
            ("metadata", "sample.geojson", {"crs": "EPSG:3857"}),
            ("metadata", "sample_point.geojson", {"geometry_type": "Point"}),
            ("metadata", "sample_point.geojson", {"geometry_type": "Polygon"}),
            ("content", "sample_point.geojson", {"geometry_type": "Point"}),
            ("content", "sample_point.geojson", {"geometry_type": "Polygon"}),
        ],
    )
    def test_geojson(self, local_client: TestClient, mode: str, fixture: str, metadata: dict) -> None:
        form = {**GEOJSON_FORM, "expected_metadata": metadata}
        path = DATA / fixture
        uploaded = upload(local_client, mode, form, path)
        local = _local(local_client, mode, form, path)
        assert uploaded.status_code == local.status_code == 200
        assert _outcome(local) == _outcome(uploaded)

    @pytest.mark.parametrize(
        ("extensions", "expected_status"),
        [([".shx", ".dbf", ".prj"], "SUCCESS"), ([".shx"], "FAILURE")],
    )
    def test_shapefile(
        self, local_client: TestClient, sample_shapefile: Path, extensions: list[str], expected_status: str
    ) -> None:
        secondary = [sample_shapefile.with_suffix(ext) for ext in extensions]
        uploaded = upload(local_client, "metadata", SHAPEFILE_FORM, sample_shapefile, secondary)
        local = _local(local_client, "metadata", SHAPEFILE_FORM, sample_shapefile, secondary)
        assert uploaded.status_code == local.status_code == 200
        assert _outcome(local) == _outcome(uploaded)
        assert local.json()["status"] == expected_status

    def test_files_are_not_deleted(self, local_client: TestClient, sample_shapefile: Path) -> None:
        secondary = [sample_shapefile.with_suffix(ext) for ext in (".shx", ".dbf", ".prj")]
        _local(local_client, "metadata", SHAPEFILE_FORM, sample_shapefile, secondary)
        assert all(p.exists() for p in [sample_shapefile, *secondary])


class TestAccessControl:
    def test_disabled_without_shared_dirs(self) -> None:
        client = _client_with_shared_dirs()
        response = _local(client, "metadata", GEOJSON_FORM, DATA / "sample.geojson")
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"]

    def test_outside_shared_dirs(self, local_client: TestClient) -> None:
        response = _local(local_client, "metadata", GEOJSON_FORM, "/etc/passwd")
        assert response.status_code == 403

    def test_dotdot_escape(self, local_client: TestClient) -> None:
        response = _local(local_client, "metadata", GEOJSON_FORM, f"{DATA}/../../../pyproject.toml")
        assert response.status_code == 403

    def test_symlink_escape(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "sample.geojson").symlink_to(DATA / "sample.geojson")
        client = _client_with_shared_dirs(shared)
        response = _local(client, "metadata", GEOJSON_FORM, shared / "sample.geojson")
        assert response.status_code == 403

    def test_secondary_file_outside_shared_dirs(self, local_client: TestClient, sample_shapefile: Path) -> None:
        response = _local(local_client, "metadata", SHAPEFILE_FORM, sample_shapefile, [Path("/etc/passwd")])
        assert response.status_code == 403

    def test_missing_file(self, local_client: TestClient) -> None:
        response = _local(local_client, "metadata", GEOJSON_FORM, DATA / "missing.geojson")
        assert response.status_code == 404

    def test_relative_path(self, local_client: TestClient) -> None:
        response = _local(local_client, "metadata", GEOJSON_FORM, "sample.geojson")
        assert response.status_code == 400

    def test_missing_file_path(self, local_client: TestClient) -> None:
        response = local_client.post("/api/v1/validate/metadata/local", json=GEOJSON_FORM)
        assert response.status_code == 422


class TestRequestErrorsLikeUpload:
    def test_unknown_format(self, local_client: TestClient) -> None:
        form = {**GEOJSON_FORM, "format_identifier": "format_99999"}
        response = _local(local_client, "metadata", form, DATA / "sample.geojson")
        assert response.status_code == 400

    def test_request_checked_before_paths(self, local_client: TestClient) -> None:
        """A request that cannot be validated is rejected before its paths are looked at."""
        form = {**GEOJSON_FORM, "format_identifier": "format_99999"}
        response = _local(local_client, "metadata", form, "/etc/passwd")
        assert response.status_code == 400

    @pytest.mark.parametrize(
        ("metadata", "status_code"),
        [
            pytest.param({"encoding": "utf-8"}, 400, id="unsupported-key"),
            pytest.param({"crs": "totally-bogus-crs-string"}, 400, id="invalid-value"),
            pytest.param({"crs": 4326}, 422, id="non-string-value"),
        ],
    )
    def test_invalid_metadata(self, local_client: TestClient, metadata: dict, status_code: int) -> None:
        form = {**GEOJSON_FORM, "expected_metadata": metadata}
        response = _local(local_client, "metadata", form, DATA / "sample.geojson")
        assert response.status_code == status_code


class TestServerTiming:
    _ENTRY = r"{name};dur=\d+\.\d"

    def test_upload(self, local_client: TestClient) -> None:
        response = upload(local_client, "metadata", GEOJSON_FORM, DATA / "sample.geojson")
        expected = ", ".join(self._ENTRY.format(name=n) for n in ("receive", "validate"))
        assert re.fullmatch(expected, response.headers["server-timing"])

    def test_local(self, local_client: TestClient) -> None:
        response = _local(local_client, "metadata", GEOJSON_FORM, DATA / "sample.geojson")
        expected = ", ".join(self._ENTRY.format(name=n) for n in ("resolve", "validate"))
        assert re.fullmatch(expected, response.headers["server-timing"])
