"""Fixtures for the integration tests."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from api.app import create_app
from api.dependencies import get_format_translator, load_format_translator

from ..conftest import DATA, EXAMPLE_NAMESPACE, EXAMPLE_ONTOLOGY, MAPPINGS

# Validation form fields for formats of the example ontology.
GEOJSON_FORM = {"ontology_namespace": EXAMPLE_NAMESPACE, "format_identifier": "GeoJSON"}
SHAPEFILE_FORM = {"ontology_namespace": EXAMPLE_NAMESPACE, "format_identifier": "Shapefile"}


def create_test_app() -> FastAPI:
    """Create the app with the example mapping instead of ``mappings/``."""
    app = create_app()
    translator = load_format_translator(MAPPINGS)
    app.dependency_overrides[get_format_translator] = lambda: translator
    return app


def upload(client: TestClient, mode: str, form: dict, primary: Path, secondary: list[Path] = []) -> Response:
    """POST ``primary`` and ``secondary`` files with ``form`` to ``/validate/{mode}``.

    An ``expected_metadata`` dict in ``form`` is sent as a JSON string field.
    """
    if isinstance(form.get("expected_metadata"), dict):
        form = form | {"expected_metadata": json.dumps(form["expected_metadata"])}
    handles = [p.open("rb") for p in [primary, *secondary]]
    try:
        files = [("file", (primary.name, handles[0], "application/octet-stream"))]
        files += [("secondary_files", (p.name, h, "application/octet-stream")) for p, h in zip(secondary, handles[1:])]
        return client.post(f"/api/v1/validate/{mode}", files=files, data=form)
    finally:
        for h in handles:
            h.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_test_app())


@pytest.fixture
def ontology_file() -> Path:
    return EXAMPLE_ONTOLOGY


@pytest.fixture
def sample_geojson() -> Path:
    return DATA / "sample.geojson"


@pytest.fixture
def sample_geojson_with_point() -> Path:
    return DATA / "sample_point.geojson"


@pytest.fixture
def sample_shapefile(tmp_path: Path) -> Path:
    """Write a small point shapefile and return the path of the .shp."""
    import fiona
    from fiona.crs import CRS

    shp = tmp_path / "points.shp"
    schema = {"geometry": "Point", "properties": {"name": "str"}}
    with fiona.open(shp, "w", driver="ESRI Shapefile", schema=schema, crs=CRS.from_epsg(4326)) as dst:
        dst.write({"geometry": {"type": "Point", "coordinates": (1.0, 2.0)}, "properties": {"name": "a"}})
    return shp
