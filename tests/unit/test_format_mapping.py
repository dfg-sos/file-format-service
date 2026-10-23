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
    """The example mapping, keyed by full format IRI."""

    def test_to_local_known_format(self, translator: FormatTranslator) -> None:
        assert translator.to_local(EXAMPLE_NAMESPACE + "Shapefile") == FormatIdentifier.SHAPEFILE

    def test_to_local_abstract_format(self, translator: FormatTranslator) -> None:
        assert translator.to_local(EXAMPLE_NAMESPACE + "Vector") == FormatIdentifier.get("GISVector")

    @pytest.mark.parametrize(
        "iri",
        [
            pytest.param("http://unknown.org/Shapefile", id="other-namespace"),
            pytest.param(EXAMPLE_NAMESPACE + "format_9999", id="unknown-identifier"),
        ],
    )
    def test_to_local_unmapped(self, translator: FormatTranslator, iri: str) -> None:
        assert translator.to_local(iri) is None

    def test_to_external(self, translator: FormatTranslator) -> None:
        assert translator.to_external(FormatIdentifier.SHAPEFILE) == EXAMPLE_NAMESPACE + "Shapefile"


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
        self._write_mapping(tmp_path, "a", "https://a.org/fmt#", {"Roads": "Shapefile"})
        self._write_mapping(tmp_path, "b", "https://b.org/fmt#", {"Elevation": "GeoTIFF"})
        translator = load_format_translator(tmp_path)
        assert translator.to_local("https://a.org/fmt#Roads") == FormatIdentifier.SHAPEFILE
        assert translator.to_local("https://b.org/fmt#Elevation") == FormatIdentifier.GEOTIFF

    def test_same_iri_in_two_files_must_agree(self, tmp_path: Path) -> None:
        self._write_mapping(tmp_path, "a", "https://a.org/fmt#", {"Roads": "Shapefile"})
        self._write_mapping(tmp_path, "b", "https://a.org/fmt#", {"Roads": "GeoJSON"})
        with pytest.raises(ValueError, match=r"b\.json: .*https://a\.org/fmt#Roads"):
            load_format_translator(tmp_path)

    def test_same_iri_in_two_files_may_repeat(self, tmp_path: Path) -> None:
        self._write_mapping(tmp_path, "a", "https://a.org/fmt#", {"Roads": "Shapefile"})
        self._write_mapping(tmp_path, "b", "https://a.org/fmt#", {"Roads": "Shapefile", "Elevation": "GeoTIFF"})
        translator = load_format_translator(tmp_path)
        assert sorted(translator.iris()) == ["https://a.org/fmt#Elevation", "https://a.org/fmt#Roads"]

    def test_unknown_format_identifier_rejected(self, tmp_path: Path) -> None:
        self._write_mapping(tmp_path, "a", "https://a.org/fmt#", {"Roads": "esrijson"})
        with pytest.raises(ValueError, match=r"a\.json: .*esrijson"):
            load_format_translator(tmp_path)

    def test_missing_dir_loads_nothing_and_warns(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            translator = load_format_translator(tmp_path / "absent")
        assert translator.iris() == []
        assert "No mapping files" in caplog.text

    def test_empty_dir_warns(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            load_format_translator(tmp_path)
        assert "No mapping files" in caplog.text
