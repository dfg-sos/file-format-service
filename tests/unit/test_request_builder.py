"""Unit tests for the ``HTTPValidationRequestBuilder``."""

from pathlib import Path

import pytest
from format_validator import (
    EOMetadata,
    FileInput,
    FormatIdentifier,
    FormatTranslator,
    MultiFileInput,
    ValidationMode,
    ValidationRequest,
)

from adapter.request_builder import HTTPValidationRequestBuilder, ValidationRequestDTO


@pytest.fixture
def shp(tmp_path: Path) -> Path:
    path = tmp_path / "roads.shp"
    path.touch()
    return path


def _dto(file_path: Path, **overrides) -> ValidationRequestDTO:
    fields = {
        "ontology_namespace": "https://w3id.org/sos/eo-formats#",
        "format_identifier": "Shapefile",
        "mode": ValidationMode.FULL,
        "file_path": file_path,
    }
    return ValidationRequestDTO(**(fields | overrides))


def _build(dto: ValidationRequestDTO, translator: FormatTranslator) -> ValidationRequest:
    """Build a request that is expected to succeed."""
    request = HTTPValidationRequestBuilder(dto, translator).build()
    assert request is not None
    return request


def _metadata(request: ValidationRequest) -> EOMetadata:
    assert isinstance(request.metadata, EOMetadata)
    return request.metadata


class TestBuildFailure:
    def test_unknown_format_returns_none(self, shp: Path, translator: FormatTranslator) -> None:
        dto = _dto(shp, format_identifier="format_99999")
        assert HTTPValidationRequestBuilder(dto, translator).build() is None

    def test_invalid_crs_returns_none(self, shp: Path, translator: FormatTranslator) -> None:
        dto = _dto(shp, expected_crs="not-a-crs")
        assert HTTPValidationRequestBuilder(dto, translator).build() is None

    def test_invalid_geometry_type_returns_none(self, shp: Path, translator: FormatTranslator) -> None:
        dto = _dto(shp, expected_geometry_type="NotAGeometry")
        assert HTTPValidationRequestBuilder(dto, translator).build() is None


class TestFileInput:
    def test_single_file(self, shp: Path, translator: FormatTranslator) -> None:
        request = _build(_dto(shp), translator)
        assert type(request.actual_file) is FileInput
        assert request.actual_file.path == shp

    def test_secondary_files(self, shp: Path, translator: FormatTranslator) -> None:
        secondary = {shp.with_suffix(".shx"), shp.with_suffix(".dbf")}
        request = _build(_dto(shp, secondary_file_paths=secondary), translator)
        assert isinstance(request.actual_file, MultiFileInput)
        assert request.actual_file.files() == {shp} | secondary


class TestPassThrough:
    def test_format_and_mode(self, shp: Path, translator: FormatTranslator) -> None:
        request = _build(_dto(shp, mode=ValidationMode.STRUCTURAL), translator)
        assert request.format_identifier == FormatIdentifier.SHAPEFILE
        assert request.mode == ValidationMode.STRUCTURAL

    def test_metadata(self, shp: Path, translator: FormatTranslator) -> None:
        dto = _dto(shp, expected_crs="EPSG:4326", expected_geometry_type="Point")
        metadata = _metadata(_build(dto, translator))
        assert metadata.crs is not None and metadata.crs.to_epsg() == 4326
        assert metadata.geometry_type is not None and metadata.geometry_type.name == "POINT"

    def test_no_metadata(self, shp: Path, translator: FormatTranslator) -> None:
        metadata = _metadata(_build(_dto(shp), translator))
        assert metadata.crs is None
        assert metadata.geometry_type is None
