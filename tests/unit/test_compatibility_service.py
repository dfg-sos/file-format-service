"""Unit tests for the ``CompatibilityService``."""

from core import CompatibilityResult, FormatOntology
from service.compatibility_service import CompatibilityService

EXAMPLE_ORG = "http://example.org/"


class TestCheck:
    def test_same_format_is_compatible(self, edam_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(
            expected="format_4119",
            actual="format_4119",
            ontology=edam_ontology,
        )
        assert isinstance(result, CompatibilityResult)
        assert result.compatible is True

    def test_subclass_format_is_compatible(self, edam_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(
            expected="format_4125",  # raster
            actual="format_4109",  # geotiff
            ontology=edam_ontology,
        )
        assert result.compatible is True

    def test_incompatible_formats(self, edam_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(
            expected="format_4109",  # geotiff
            actual="format_4119",  # shapefile
            ontology=edam_ontology,
        )
        assert result.compatible is False

    def test_formats_are_passed_through(self, toy_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(expected="vector", actual="shapefile", ontology=toy_ontology)
        assert result.expected == "vector"
        assert result.actual == "shapefile"

    def test_compatible_message(self, toy_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(expected="vector", actual="shapefile", ontology=toy_ontology)
        assert result.message.startswith("'shapefile' is compatible with 'vector'")

    def test_incompatible_message(self, toy_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(expected="shapefile", actual="vector", ontology=toy_ontology)
        assert result.message.startswith("'vector' is **not** compatible with 'shapefile'")

    def test_result_truthiness_follows_compatible(self, toy_ontology: FormatOntology) -> None:
        assert bool(CompatibilityService.check(expected="vector", actual="shapefile", ontology=toy_ontology))
        assert not CompatibilityService.check(expected="shapefile", actual="vector", ontology=toy_ontology)


class TestDelegation:
    def test_get_parents(self, toy_ontology: FormatOntology) -> None:
        assert CompatibilityService.get_parents("shapefile", toy_ontology) == [EXAMPLE_ORG + "vector"]

    def test_get_equivalents(self, toy_ontology: FormatOntology) -> None:
        assert CompatibilityService.get_equivalents("tiff", toy_ontology) == [EXAMPLE_ORG + "geotiff"]
