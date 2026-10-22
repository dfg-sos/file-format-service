"""Unit tests for the ``FormatTranslator`` integration."""

import json
import logging
from pathlib import Path

import pytest
from format_validator import FormatIdentifier, FormatTranslator

from api.dependencies import load_format_translator
from core import FormatOntology

from ..conftest import EXAMPLE_NAMESPACE, MAPPINGS


class TestFormatTranslator:
    """Tests for format identifier resolution via the official translator."""

    def test_to_local_known_format(self, translator: FormatTranslator) -> None:
        result = translator.to_local("Shapefile", EXAMPLE_NAMESPACE)
        assert result is not None
        assert result == FormatIdentifier.SHAPEFILE

    def test_to_local_unknown_ontology(self, translator: FormatTranslator) -> None:
        result = translator.to_local("Shapefile", "http://unknown.org")
        # Falls through to search all loaded ontologies
        assert result is not None
        assert result == FormatIdentifier.SHAPEFILE

    def test_to_local_unknown_format(self, translator: FormatTranslator) -> None:
        result = translator.to_local("format_9999", EXAMPLE_NAMESPACE)
        assert result is None

    def test_to_external(self, translator: FormatTranslator) -> None:
        result = translator.to_external("shapefile", EXAMPLE_NAMESPACE)
        assert result == "Shapefile"

    def test_get_loaded_ontologies(self, translator: FormatTranslator) -> None:
        ontologies = translator.get_loaded_ontologies()
        assert EXAMPLE_NAMESPACE in ontologies


class TestExampleMapping:
    """The example mapping and ontology are documented as a pair, keep them consistent."""

    def test_every_mapped_identifier_is_a_class(self, example_ontology: FormatOntology) -> None:
        mapping = json.loads((MAPPINGS / "example-formats.json").read_text())
        assert mapping["ontology_uri"] == EXAMPLE_NAMESPACE
        undefined = [fmt for fmt in mapping["mappings"] if not example_ontology.is_defined(fmt)]
        assert undefined == []


class TestLoadFormatTranslator:
    """Tests for loading the mappings directory."""

    @staticmethod
    def _write_mapping(directory: Path, name: str, ontology_uri: str, mappings: dict[str, str]) -> None:
        (directory / f"{name}.json").write_text(json.dumps({"ontology_uri": ontology_uri, "mappings": mappings}))

    def test_loads_every_mapping_file(self, tmp_path: Path) -> None:
        self._write_mapping(tmp_path, "a", "https://a.org/fmt#", {"Roads": "shapefile"})
        self._write_mapping(tmp_path, "b", "https://b.org/fmt#", {"Elevation": "geotiff"})
        translator = load_format_translator(tmp_path)
        assert translator.to_local("Roads", "https://a.org/fmt#") == FormatIdentifier.SHAPEFILE
        assert translator.to_local("Elevation", "https://b.org/fmt#") == FormatIdentifier.GEOTIFF

    def test_missing_dir_loads_nothing_and_warns(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            translator = load_format_translator(tmp_path / "absent")
        assert translator.get_loaded_ontologies() == []
        assert "No mapping files" in caplog.text

    def test_empty_dir_warns(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            load_format_translator(tmp_path)
        assert "No mapping files" in caplog.text
