"""Fixture paths and fixtures shared by the unit and integration tests."""

from collections.abc import Callable
from pathlib import Path

import pytest
from format_validator import FormatTranslator

from api.dependencies import load_format_translator
from core import FormatOntology

FIXTURES = Path(__file__).parent / "fixtures"
ONTOLOGIES = FIXTURES / "ontologies"
MAPPINGS = FIXTURES / "mappings"
DATA = FIXTURES / "data"

# Example ontology for tests and documentation, mapped by MAPPINGS.
EXAMPLE_ONTOLOGY = ONTOLOGIES / "example-formats.ttl"
EXAMPLE_NAMESPACE = "https://example.org/formats#"

# Serialisations the ontology endpoints accept: file extension -> rdflib format.
SERIALISATIONS = {
    ".owl": "xml",
    ".rdf": "xml",
    ".ttl": "turtle",
    ".nt": "nt",
    ".n3": "n3",
    ".jsonld": "json-ld",
}


@pytest.fixture(scope="session")
def example_ontology() -> FormatOntology:
    return FormatOntology.from_source(EXAMPLE_ONTOLOGY)


@pytest.fixture
def serialise_example(example_ontology: FormatOntology) -> Callable[[str], bytes]:
    """Return a function serialising the example ontology as the given rdflib format."""
    return lambda rdf_format: example_ontology.graph.serialize(format=rdf_format, encoding="utf-8")


@pytest.fixture(params=SERIALISATIONS.items(), ids=lambda item: item[0])
def example_serialisation(
    request: pytest.FixtureRequest, serialise_example: Callable[[str], bytes]
) -> tuple[str, bytes]:
    """The example ontology as ``(file extension, content)``, once per serialisation."""
    extension, rdf_format = request.param
    return extension, serialise_example(rdf_format)


@pytest.fixture
def translator() -> FormatTranslator:
    """Translator with the example mapping."""
    return load_format_translator(MAPPINGS)
