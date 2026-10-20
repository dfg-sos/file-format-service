"""Unit tests for the ``FormatTranslator`` integration."""

from format_validator import FormatIdentifier, FormatTranslator


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
