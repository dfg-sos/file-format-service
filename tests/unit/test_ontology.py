"""Unit tests for ``FormatOntology``."""

from pathlib import Path

import pytest
from rdflib import RDF, RDFS, Graph

from core import FormatOntology

from ..conftest import EXAMPLE_NAMESPACE
from .conftest import EDGE_CASE_NAMESPACE


class TestLoading:
    def test_from_bytes_turtle(self, edge_case_ontology: FormatOntology) -> None:
        assert len(edge_case_ontology.graph) > 0

    def test_from_bytes_invalid_content_raises(self) -> None:
        with pytest.raises(Exception):
            FormatOntology.from_bytes(b"this is not rdf", format="turtle")

    def test_from_source_invalid_file_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.ttl"
        bad.write_text("this is not rdf")
        with pytest.raises(Exception):
            FormatOntology.from_source(bad)


class TestNamespaceInference:
    def test_uses_owl_ontology_subject(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology._namespace == EDGE_CASE_NAMESPACE

    def test_falls_back_to_most_common_class_prefix(self) -> None:
        ttl = b"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <http://a.org/x/one> a owl:Class .
        <http://a.org/x/two> a owl:Class .
        <http://b.org/y/three> a owl:Class .
        """
        ontology = FormatOntology.from_bytes(ttl, format="turtle")
        assert ontology._namespace == "http://a.org/x/"

    def test_empty_graph_has_no_namespace(self) -> None:
        assert FormatOntology(Graph())._namespace is None

    def test_explicit_namespace_wins(self) -> None:
        assert FormatOntology(Graph(), namespace="http://c.org/")._namespace == "http://c.org/"


class TestExpandId:
    def test_short_id_is_expanded(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology._expand_id("shapefile") == EDGE_CASE_NAMESPACE + "shapefile"

    @pytest.mark.parametrize("iri", ["http://other.org/fmt", "https://other.org/fmt"])
    def test_full_iri_is_unchanged(self, edge_case_ontology: FormatOntology, iri: str) -> None:
        assert edge_case_ontology._expand_id(iri) == iri

    @pytest.mark.parametrize("namespace", ["http://c.org", "http://c.org/"])
    def test_trailing_slash_is_normalised(self, namespace: str) -> None:
        assert FormatOntology(Graph(), namespace=namespace)._expand_id("fmt") == "http://c.org/fmt"

    def test_without_namespace_id_is_unchanged(self) -> None:
        assert FormatOntology(Graph())._expand_id("fmt") == "fmt"

    def test_hash_namespace(self) -> None:
        ontology = FormatOntology(Graph(), namespace="http://c.org/onto#")
        assert ontology._expand_id("fmt") == "http://c.org/onto#fmt"

    def test_hash_namespace_inferred_from_classes(self) -> None:
        ttl = b"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <http://c.org/onto#vector> a owl:Class .
        <http://c.org/onto#raster> a owl:Class .
        """
        ontology = FormatOntology.from_bytes(ttl, format="turtle")
        assert ontology.is_defined("vector")

    def test_hash_classes_under_ontology_iri_without_separator(self) -> None:
        ttl = b"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <http://c.org/onto> a owl:Ontology .
        <http://c.org/onto#vector> a owl:Class .
        """
        ontology = FormatOntology.from_bytes(ttl, format="turtle")
        assert ontology._expand_id("vector") == "http://c.org/onto#vector"
        assert ontology._expand_id("unknown") == "http://c.org/onto/unknown"

    def test_example_short_id(self, example_ontology: FormatOntology) -> None:
        assert example_ontology._expand_id("GeoTIFF") == EXAMPLE_NAMESPACE + "GeoTIFF"


class TestIsDefined:
    def test_defined_format(self, example_ontology: FormatOntology) -> None:
        assert example_ontology.is_defined("Shapefile") is True

    def test_defined_format_full_iri(self, example_ontology: FormatOntology) -> None:
        assert example_ontology.is_defined(EXAMPLE_NAMESPACE + "Shapefile") is True

    def test_undefined_format(self, example_ontology: FormatOntology) -> None:
        assert example_ontology.is_defined("format_99999") is False

    def test_rdfs_class_is_defined(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_defined("rdfs_only") is True

    def test_only_referenced_as_object_is_undefined(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_defined("undeclared") is False


class TestIsSubclass:
    def test_identity(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("vector", "vector") is True

    def test_identity_holds_for_undefined_format(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("nonexistent", "nonexistent") is True

    def test_short_id_and_full_iri_are_identical(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("vector", EDGE_CASE_NAMESPACE + "vector") is True

    def test_direct_subclass(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("shapefile", "vector") is True

    def test_transitive_subclass(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("zipped_shapefile", "vector") is True

    def test_superclass_is_not_subclass(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("vector", "shapefile") is False

    def test_unrelated(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("geotiff", "vector") is False

    def test_equivalent_class_forward(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("tiff", "geotiff") is True

    def test_equivalent_class_backward(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("geotiff", "tiff") is True

    def test_subclass_via_equivalent_class(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("tiff", "raster") is True

    def test_cycle_terminates(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("cyc_a", "vector") is False

    def test_cycle_members_are_mutual_subclasses(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.is_subclass("cyc_a", "cyc_b") is True
        assert edge_case_ontology.is_subclass("cyc_b", "cyc_a") is True


class TestAreCompatible:
    def test_actual_subclass_of_expected(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.are_compatible(expected="vector", actual="shapefile") is True

    def test_actual_superclass_of_expected(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.are_compatible(expected="shapefile", actual="vector") is False


class TestIntrospection:
    def test_label(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_label("shapefile") == "Shapefile"

    def test_label_missing(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_label("vector") is None

    def test_comment(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_comment("shapefile") == "Composite vector format."

    def test_comment_missing(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_comment("vector") is None

    def test_values(self, edge_case_ontology: FormatOntology) -> None:
        values = edge_case_ontology.get_values("shapefile", EDGE_CASE_NAMESPACE + "file_extension")
        assert sorted(values) == ["dbf", "shp", "shx"]

    def test_values_missing(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_values("vector", EDGE_CASE_NAMESPACE + "file_extension") == []

    def test_annotations(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_annotations("shapefile") == {
            EDGE_CASE_NAMESPACE + "file_extension": ["dbf", "shp", "shx"],
            str(RDFS.comment): ["Composite vector format."],
            str(RDFS.label): ["Shapefile"],
        }

    def test_annotations_skip_structural_predicates(self, edge_case_ontology: FormatOntology) -> None:
        annotations = edge_case_ontology.get_annotations("shapefile")
        assert str(RDF.type) not in annotations
        assert str(RDFS.subClassOf) not in annotations

    def test_annotations_undefined_format(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_annotations("format_99999") == {}

    def test_parents(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_parents("shapefile") == [EDGE_CASE_NAMESPACE + "vector"]

    def test_parents_are_direct_only(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_parents("zipped_shapefile") == [EDGE_CASE_NAMESPACE + "shapefile"]

    def test_children(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_children("vector") == [EDGE_CASE_NAMESPACE + "shapefile"]

    def test_children_missing(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_children("zipped_shapefile") == []

    def test_equivalents_both_directions(self, edge_case_ontology: FormatOntology) -> None:
        assert edge_case_ontology.get_equivalents("tiff") == [EDGE_CASE_NAMESPACE + "geotiff"]
        assert edge_case_ontology.get_equivalents("geotiff") == [EDGE_CASE_NAMESPACE + "tiff"]
