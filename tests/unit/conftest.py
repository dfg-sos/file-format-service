"""Shared fixtures for the unit tests."""

from pathlib import Path

import pytest
from format_validator import FormatTranslator

from core import FormatOntology

REPO_ROOT = Path(__file__).parent.parent.parent

# A tiny ontology covering the relationship shapes ``FormatOntology`` has to
# handle: direct and transitive subclasses, equivalence, cycles, an
# ``rdfs:Class``-typed class and a parent that is never declared as a class.
TOY_TTL = b"""
@prefix ex:   <http://example.org/> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<http://example.org/> a owl:Ontology .

ex:vector a owl:Class .

ex:shapefile a owl:Class ;
    rdfs:subClassOf ex:vector ;
    rdfs:label "Shapefile" ;
    rdfs:comment "Composite vector format." ;
    ex:file_extension "shp", "shx", "dbf" .

ex:zipped_shapefile a owl:Class ;
    rdfs:subClassOf ex:shapefile .

ex:raster a owl:Class .

ex:geotiff a owl:Class ;
    rdfs:subClassOf ex:raster .

ex:tiff a owl:Class ;
    owl:equivalentClass ex:geotiff .

ex:cyc_a a owl:Class ;
    rdfs:subClassOf ex:cyc_b .

ex:cyc_b a owl:Class ;
    rdfs:subClassOf ex:cyc_a .

ex:rdfs_only a rdfs:Class .

ex:child_of_undeclared a owl:Class ;
    rdfs:subClassOf ex:undeclared .
"""


@pytest.fixture(scope="session")
def eo_ontology() -> FormatOntology:
    return FormatOntology.from_source(REPO_ROOT / "ontology" / "eo-formats.owl")


@pytest.fixture
def toy_ontology() -> FormatOntology:
    return FormatOntology.from_bytes(TOY_TTL, format="turtle")


@pytest.fixture
def translator() -> FormatTranslator:
    return FormatTranslator(REPO_ROOT / "mappings")
