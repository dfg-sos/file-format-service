import pytest
from pathlib import Path
from core.ontology import FormatOntology


@pytest.fixture
def ontology() -> FormatOntology:
    return FormatOntology.from_source(Path(__file__).parent / "edamontology_adapted.org.owl")
