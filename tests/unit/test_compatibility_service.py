"""Unit tests for the ``CompatibilityService``."""

from core import CompatibilityResult, FormatOntology
from service.compatibility_service import CompatibilityService

from .conftest import EDGE_CASE_NAMESPACE


class TestCheck:
    def test_same_format_is_compatible(self, example_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(
            expected="Shapefile",
            actual="Shapefile",
            ontology=example_ontology,
        )
        assert isinstance(result, CompatibilityResult)
        assert result.compatible is True

    def test_subclass_format_is_compatible(self, example_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(
            expected="Raster",
            actual="GeoTIFF",
            ontology=example_ontology,
        )
        assert result.compatible is True

    def test_incompatible_formats(self, example_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(
            expected="GeoTIFF",
            actual="Shapefile",
            ontology=example_ontology,
        )
        assert result.compatible is False

    def test_formats_are_passed_through(self, edge_case_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(expected="vector", actual="shapefile", ontology=edge_case_ontology)
        assert result.expected == "vector"
        assert result.actual == "shapefile"

    def test_compatible_message(self, edge_case_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(expected="vector", actual="shapefile", ontology=edge_case_ontology)
        assert result.message.startswith("'shapefile' is compatible with 'vector'")

    def test_incompatible_message(self, edge_case_ontology: FormatOntology) -> None:
        result = CompatibilityService.check(expected="shapefile", actual="vector", ontology=edge_case_ontology)
        assert result.message.startswith("'vector' is **not** compatible with 'shapefile'")

    def test_result_truthiness_follows_compatible(self, edge_case_ontology: FormatOntology) -> None:
        assert bool(CompatibilityService.check(expected="vector", actual="shapefile", ontology=edge_case_ontology))
        assert not CompatibilityService.check(expected="shapefile", actual="vector", ontology=edge_case_ontology)


class TestDelegation:
    def test_get_parents(self, edge_case_ontology: FormatOntology) -> None:
        assert CompatibilityService.get_parents("shapefile", edge_case_ontology) == [EDGE_CASE_NAMESPACE + "vector"]

    def test_get_equivalents(self, edge_case_ontology: FormatOntology) -> None:
        assert CompatibilityService.get_equivalents("tiff", edge_case_ontology) == [EDGE_CASE_NAMESPACE + "geotiff"]
