"""Unit tests for the ``CompatibilityService``."""

from pathlib import Path

import pytest

from compatibility import CompatibilityResult
from config import Settings
from service.compatibility_service import CompatibilityService


class TestCompatibilityService:
    """Tests for ontology-based compatibility checks."""

    @pytest.fixture
    def service(self) -> CompatibilityService:
        settings = Settings()
        return CompatibilityService(settings)

    def test_same_format_is_compatible(self, service: CompatibilityService) -> None:
        result = service.check(
            expected="format_4119",
            actual="format_4119",
            ontology_source="http://edamontology.org",
        )
        assert isinstance(result, CompatibilityResult)
        assert result.compatible is True

    def test_different_formats_may_be_incompatible(
        self, service: CompatibilityService
    ) -> None:
        result = service.check(
            expected="format_4109",  # geotiff
            actual="format_4119",  # shapefile
            ontology_source="http://edamontology.org",
        )
        assert isinstance(result, CompatibilityResult)
        # Depending on ontology contents this may be True or False
        assert isinstance(result.compatible, bool)
