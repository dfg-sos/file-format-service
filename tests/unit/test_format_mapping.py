"""Unit tests for the ``FormatTranslator`` integration."""

import json
import logging
from pathlib import Path

import pytest
from format_validator import FormatIdentifier, FormatTranslator

from api.dependencies import load_format_translator
from config import BUNDLED_MAPPINGS_DIR

EO_FORMATS = "https://w3id.org/sos/eo-formats#"


class TestFormatTranslator:
    """Tests for format identifier resolution via the official translator."""

    def test_to_local_known_format(self, translator: FormatTranslator) -> None:
        result = translator.to_local("Shapefile", "https://w3id.org/sos/eo-formats#")
        assert result is not None
        assert result == FormatIdentifier.SHAPEFILE

    def test_to_local_unknown_ontology(self, translator: FormatTranslator) -> None:
        result = translator.to_local("Shapefile", "http://unknown.org")
        # Falls through to search all loaded ontologies
        assert result is not None
        assert result == FormatIdentifier.SHAPEFILE

    def test_to_local_unknown_format(self, translator: FormatTranslator) -> None:
        result = translator.to_local("format_9999", "https://w3id.org/sos/eo-formats#")
        assert result is None

    def test_to_external(self, translator: FormatTranslator) -> None:
        result = translator.to_external("shapefile", "https://w3id.org/sos/eo-formats#")
        assert result == "Shapefile"

    def test_get_loaded_ontologies(self, translator: FormatTranslator) -> None:
        ontologies = translator.get_loaded_ontologies()
        assert "https://w3id.org/sos/eo-formats#" in ontologies


class TestLoadFormatTranslator:
    """Tests for combining the bundled mappings with custom ones."""

    @staticmethod
    def _write_mapping(directory: Path, ontology_uri: str, mappings: dict[str, str]) -> None:
        directory.mkdir(exist_ok=True)
        (directory / "custom.json").write_text(json.dumps({"ontology_uri": ontology_uri, "mappings": mappings}))

    def test_missing_custom_dir_loads_bundled(self, tmp_path: Path) -> None:
        translator = load_format_translator(BUNDLED_MAPPINGS_DIR, tmp_path / "absent")
        assert translator.get_loaded_ontologies() == [EO_FORMATS]

    def test_custom_mapping_is_added(self, tmp_path: Path) -> None:
        self._write_mapping(tmp_path, "https://example.org/fmt#", {"Roads": "shapefile"})
        translator = load_format_translator(BUNDLED_MAPPINGS_DIR, tmp_path)
        assert translator.to_local("Roads", "https://example.org/fmt#") == FormatIdentifier.SHAPEFILE
        assert translator.to_local("Shapefile", EO_FORMATS) == FormatIdentifier.SHAPEFILE

    def test_custom_mapping_overrides_bundled(self, tmp_path: Path) -> None:
        self._write_mapping(tmp_path, EO_FORMATS, {"Roads": "shapefile"})
        translator = load_format_translator(BUNDLED_MAPPINGS_DIR, tmp_path)
        assert translator.to_external("shapefile", EO_FORMATS) == "Roads"

    def test_empty_custom_dir_warns(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            load_format_translator(BUNDLED_MAPPINGS_DIR, tmp_path)
        assert "No mapping files" in caplog.text
