"""Integration tests for the ``/validate/basic`` endpoint."""

import re

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from .conftest import GEOJSON_FORM, SHAPEFILE_FORM

SHAPEFILE_COMPONENTS = ["/data/roads.shx", "/data/roads.dbf", "/data/roads.prj"]


def _basic(client: TestClient, form: dict, primary: str, secondary: list[str] = []) -> Response:
    body = {**form, "file_path": primary, "secondary_file_paths": secondary}
    return client.post("/api/v1/validate/basic", json=body)


def _causes(response: Response) -> list[str]:
    return [event["cause"] for event in response.json()["errors"]]


class TestOutcome:
    @pytest.mark.parametrize("path", ["/nowhere/sample.geojson", "relative/sample.geojson", "sample.GeoJSON"])
    def test_files_are_not_accessed(self, client: TestClient, path: str) -> None:
        """Only the name is checked: the file need not exist, and no shared dirs are configured."""
        response = _basic(client, GEOJSON_FORM, path)
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"

    def test_wrong_extension_fails(self, client: TestClient) -> None:
        response = _basic(client, GEOJSON_FORM, "/data/sample.tif")
        assert response.json()["status"] == "FAILURE"
        assert _causes(response) == ["extension_mismatch"]

    @pytest.mark.parametrize(
        ("secondary", "status"),
        [
            pytest.param(SHAPEFILE_COMPONENTS, "SUCCESS", id="complete"),
            pytest.param(SHAPEFILE_COMPONENTS[:2], "FAILURE", id="missing-prj"),
            pytest.param([*SHAPEFILE_COMPONENTS[:2], "/elsewhere/roads.prj"], "FAILURE", id="other-directory"),
        ],
    )
    def test_shapefile_components(self, client: TestClient, secondary: list[str], status: str) -> None:
        response = _basic(client, SHAPEFILE_FORM, "/data/roads.shp", secondary)
        assert response.json()["status"] == status


class TestRequestErrors:
    def test_unknown_format(self, client: TestClient) -> None:
        form = {**GEOJSON_FORM, "format_identifier": "format_99999"}
        assert _basic(client, form, "/data/sample.geojson").status_code == 400

    def test_missing_file_path(self, client: TestClient) -> None:
        response = client.post("/api/v1/validate/basic", json=GEOJSON_FORM)
        assert response.status_code == 422


def test_server_timing(client: TestClient) -> None:
    response = _basic(client, GEOJSON_FORM, "/data/sample.geojson")
    assert re.fullmatch(r"validate;dur=\d+\.\d", response.headers["server-timing"])
