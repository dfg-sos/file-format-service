"""Fixtures for the unit tests."""

import pytest

from core import FormatOntology

from ..conftest import ONTOLOGIES

EDGE_CASE_NAMESPACE = "http://example.org/edge-cases/"


@pytest.fixture(scope="session")
def edge_case_ontology() -> FormatOntology:
    """The relationship shapes ``FormatOntology`` has to handle, see ``edge-cases.ttl``."""
    return FormatOntology.from_source(ONTOLOGIES / "edge-cases.ttl")
