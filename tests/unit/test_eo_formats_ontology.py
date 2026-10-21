"""Consistency checks for the bundled ``ontology/eo-formats.owl``."""

import json

import pytest
from rdflib import OWL, RDF, RDFS, URIRef

from core import FormatOntology

from .conftest import REPO_ROOT

EO = "https://w3id.org/sos/eo-formats#"


def _classes(ontology: FormatOntology) -> set[URIRef]:
    return set(ontology.graph.subjects(RDF.type, OWL.Class))


def test_contains_no_edam_iris(eo_ontology: FormatOntology) -> None:
    terms = {str(term) for triple in eo_ontology.graph for term in triple}
    assert not [term for term in terms if "edamontology.org" in term]


def test_all_classes_in_eo_namespace(eo_ontology: FormatOntology) -> None:
    assert all(str(cls).startswith(EO) for cls in _classes(eo_ontology))


def test_no_dangling_parents(eo_ontology: FormatOntology) -> None:
    classes = _classes(eo_ontology)
    parents = set(eo_ontology.graph.objects(None, RDFS.subClassOf))
    assert parents - classes == set()


def test_every_class_has_a_label(eo_ontology: FormatOntology) -> None:
    unlabeled = [cls for cls in _classes(eo_ontology) if eo_ontology.get_label(str(cls)) is None]
    assert unlabeled == []


def test_every_mapped_identifier_is_a_class(eo_ontology: FormatOntology) -> None:
    mapping = json.loads((REPO_ROOT / "mappings" / "eo-formats.json").read_text())
    assert mapping["ontology_uri"] == EO
    undefined = [fmt for fmt in mapping["mappings"] if not eo_ontology.is_defined(fmt)]
    assert undefined == []


@pytest.mark.parametrize(
    ("expected", "actual", "compatible"),
    [
        ("GeoTIFF", "COG", True),
        ("Raster", "COG", True),
        ("Vector", "Shapefile", True),
        ("Raster", "Shapefile", False),
        ("COG", "GeoTIFF", False),
    ],
)
def test_hierarchy(eo_ontology: FormatOntology, expected: str, actual: str, compatible: bool) -> None:
    assert eo_ontology.are_compatible(expected, actual) is compatible
