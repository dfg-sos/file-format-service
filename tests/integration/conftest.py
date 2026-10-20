"""Shared fixtures for the integration tests."""

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
    return Path(__file__).parent.parent.parent / "ontology" / "eo-formats.owl"


@pytest.fixture
def sample_geojson() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "sample.geojson"


@pytest.fixture
def sample_geojson_with_point() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "sample_point.geojson"


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
