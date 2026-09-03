"""Unit tests for the ``CompatibilityService``."""
from pathlib import Path
import pytest

from core import CompatibilityResult, FormatOntology
from service.compatibility_service import CompatibilityService
from ..fixtures.ontology import ontology 


class TestCompatibilityService:
    """Tests for ontology-based compatibility checks."""


    def test_same_format_is_compatible(self, ontology: FormatOntology) -> None:
        result = CompatibilityService.check(
            expected="format_4119",
            actual="format_4119",
            ontology=ontology,
        )
        assert isinstance(result, CompatibilityResult)
        assert result.compatible is True

    def test_subclass_format_is_compatible(self, ontology: FormatOntology) -> None:
        result = CompatibilityService.check(
            expected="format_4125",  # raster
            actual="format_4109",  # geotiff
            ontology=ontology,
        )
        assert isinstance(result, CompatibilityResult)
        assert result.compatible is True

    def test_incompatible_formats(self, ontology: FormatOntology) -> None:
        result = CompatibilityService.check(
            expected="format_4109",  # geotiff
            actual="format_4119",  # shapefile
            ontology=ontology,
        )
        assert isinstance(result, CompatibilityResult)
        # Depending on ontology contents this may be True or False
        assert result.compatible is False
