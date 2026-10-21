"""Integration tests for the ``/validate/local`` endpoint."""

import re
from pathlib import Path, PurePosixPath

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_shared_path_resolver
from config import SharedDir
from service.shared_paths import SharedPathResolver

FIXTURES = Path(__file__).parent.parent / "fixtures"

GEOJSON = {"ontology_namespace": "https://w3id.org/sos/eo-formats#", "format_identifier": "GeoJSON"}
SHAPEFILE = {"ontology_namespace": "https://w3id.org/sos/eo-formats#", "format_identifier": "Shapefile"}


def _client_with_shared_dirs(*dirs: Path) -> TestClient:
    app = create_app()
    resolver = SharedPathResolver([SharedDir(PurePosixPath(d), d) for d in dirs])
    app.dependency_overrides[get_shared_path_resolver] = lambda: resolver
    return TestClient(app)


@pytest.fixture
def local_client(tmp_path: Path) -> TestClient:
    """Client whose service shares ``tests/fixtures`` and ``tmp_path``."""
    return _client_with_shared_dirs(FIXTURES, tmp_path)


def _upload(client: TestClient, form: dict, primary: Path, secondary: list[Path] = []):
    handles = [p.open("rb") for p in [primary, *secondary]]
    try:
        files = [("file", (primary.name, handles[0], "application/octet-stream"))]
        files += [("secondary_files", (p.name, h, "application/octet-stream")) for p, h in zip(secondary, handles[1:])]
        return client.post("/api/v1/validate", files=files, data=form)
    finally:
        for h in handles:
            h.close()


def _local(client: TestClient, form: dict, primary: Path | str, secondary: list[Path] = []):
    body = {**form, "file_path": str(primary), "secondary_file_paths": [str(p) for p in secondary]}
    return client.post("/api/v1/validate/local", json=body)


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
        ("fixture", "extra"),
        [
            ("sample.geojson", {"mode": "basic"}),
            ("sample.geojson", {"mode": "structural"}),
            ("sample.geojson", {"mode": "full"}),
            ("sample.geojson", {"mode": "full", "expected_crs": "EPSG:4326"}),
            ("sample.geojson", {"mode": "full", "expected_crs": "EPSG:3857"}),
            ("sample_point.geojson", {"mode": "full", "expected_geometry_type": "Point"}),
            ("sample_point.geojson", {"mode": "full", "expected_geometry_type": "Polygon"}),
            ("sample_point.geojson", {"mode": "full", "expected_geometry_type": "NotAGeometry"}),
        ],
    )
    def test_geojson(self, local_client: TestClient, fixture: str, extra: dict) -> None:
        form = {**GEOJSON, **extra}
        path = FIXTURES / fixture
        upload = _upload(local_client, form, path)
        local = _local(local_client, form, path)
        assert upload.status_code == local.status_code == 200
        assert _outcome(local) == _outcome(upload)

    @pytest.mark.parametrize(
        ("extensions", "expected_status"),
        [([".shx", ".dbf", ".prj"], "SUCCESS"), ([".shx"], "FAILURE")],
    )
    def test_shapefile(
        self, local_client: TestClient, sample_shapefile: Path, extensions: list[str], expected_status: str
    ) -> None:
        form = {**SHAPEFILE, "mode": "structural"}
        secondary = [sample_shapefile.with_suffix(ext) for ext in extensions]
        upload = _upload(local_client, form, sample_shapefile, secondary)
        local = _local(local_client, form, sample_shapefile, secondary)
        assert upload.status_code == local.status_code == 200
        assert _outcome(local) == _outcome(upload)
        assert local.json()["status"] == expected_status

    def test_files_are_not_deleted(self, local_client: TestClient, sample_shapefile: Path) -> None:
        secondary = [sample_shapefile.with_suffix(ext) for ext in (".shx", ".dbf", ".prj")]
        _local(local_client, {**SHAPEFILE, "mode": "structural"}, sample_shapefile, secondary)
        assert all(p.exists() for p in [sample_shapefile, *secondary])


class TestAccessControl:
    def test_disabled_without_shared_dirs(self) -> None:
        client = _client_with_shared_dirs()
        response = _local(client, GEOJSON, FIXTURES / "sample.geojson")
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"]

    def test_outside_shared_dirs(self, local_client: TestClient) -> None:
        response = _local(local_client, GEOJSON, "/etc/passwd")
        assert response.status_code == 403

    def test_dotdot_escape(self, local_client: TestClient) -> None:
        response = _local(local_client, GEOJSON, f"{FIXTURES}/../../pyproject.toml")
        assert response.status_code == 403

    def test_symlink_escape(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "sample.geojson").symlink_to(FIXTURES / "sample.geojson")
        client = _client_with_shared_dirs(shared)
        response = _local(client, GEOJSON, shared / "sample.geojson")
        assert response.status_code == 403

    def test_secondary_file_outside_shared_dirs(self, local_client: TestClient, sample_shapefile: Path) -> None:
        response = _local(local_client, SHAPEFILE, sample_shapefile, [Path("/etc/passwd")])
        assert response.status_code == 403

    def test_missing_file(self, local_client: TestClient) -> None:
        response = _local(local_client, GEOJSON, FIXTURES / "missing.geojson")
        assert response.status_code == 404

    def test_relative_path(self, local_client: TestClient) -> None:
        response = _local(local_client, GEOJSON, "sample.geojson")
        assert response.status_code == 400

    def test_missing_file_path(self, local_client: TestClient) -> None:
        response = local_client.post("/api/v1/validate/local", json=GEOJSON)
        assert response.status_code == 422


class TestRequestErrorsLikeUpload:
    def test_unknown_format(self, local_client: TestClient) -> None:
        form = {**GEOJSON, "format_identifier": "format_99999"}
        response = _local(local_client, form, FIXTURES / "sample.geojson")
        assert response.status_code == 400

    def test_invalid_mode(self, local_client: TestClient) -> None:
        form = {**GEOJSON, "mode": "thorough"}
        response = _local(local_client, form, FIXTURES / "sample.geojson")
        assert response.status_code == 400


class TestServerTiming:
    _ENTRY = r"{name};dur=\d+\.\d"

    def test_upload(self, local_client: TestClient) -> None:
        response = _upload(local_client, GEOJSON, FIXTURES / "sample.geojson")
        expected = ", ".join(self._ENTRY.format(name=n) for n in ("receive", "validate"))
        assert re.fullmatch(expected, response.headers["server-timing"])

    def test_local(self, local_client: TestClient) -> None:
        response = _local(local_client, GEOJSON, FIXTURES / "sample.geojson")
        expected = ", ".join(self._ENTRY.format(name=n) for n in ("resolve", "validate"))
        assert re.fullmatch(expected, response.headers["server-timing"])
