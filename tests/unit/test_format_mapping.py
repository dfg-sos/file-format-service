"""Unit tests for the ``FormatTranslator`` integration."""

from pathlib import Path

import pytest

from format_validator import FormatIdentifier, FormatTranslator


class TestFormatTranslator:
    """Tests for format identifier resolution via the official translator."""

    @pytest.fixture
    def translator(self) -> FormatTranslator:
        return FormatTranslator(Path("mappings"))

    def test_to_local_known_format(self, translator: FormatTranslator) -> None:
        result = translator.to_local("format_4119", "http://edamontology.org")
        assert result is not None
        assert result == FormatIdentifier.SHAPEFILE

    def test_to_local_unknown_ontology(self, translator: FormatTranslator) -> None:
        result = translator.to_local("format_4119", "http://unknown.org")
        # Falls through to search all loaded ontologies
        assert result is not None
        assert result == FormatIdentifier.SHAPEFILE

    def test_to_local_unknown_format(self, translator: FormatTranslator) -> None:
        result = translator.to_local("format_9999", "http://edamontology.org")
        assert result is None

    def test_to_external(self, translator: FormatTranslator) -> None:
        result = translator.to_external("shapefile", "http://edamontology.org")
        assert result == "format_4119"

    def test_get_loaded_ontologies(self, translator: FormatTranslator) -> None:
        ontologies = translator.get_loaded_ontologies()
        assert "http://edamontology.org" in ontologies
