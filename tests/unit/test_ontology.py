"""Unit tests for ``FormatOntology``."""

from pathlib import Path

import pytest
from rdflib import Graph

from core import FormatOntology

EX = "http://example.org/"


class TestLoading:
    def test_from_bytes_turtle(self, toy_ontology: FormatOntology) -> None:
        assert len(toy_ontology.graph) > 0

    def test_from_bytes_invalid_content_raises(self) -> None:
        with pytest.raises(Exception):
            FormatOntology.from_bytes(b"this is not rdf", format="turtle")

    def test_from_source_invalid_file_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.ttl"
        bad.write_text("this is not rdf")
        with pytest.raises(Exception):
            FormatOntology.from_source(bad)


class TestNamespaceInference:
    def test_uses_owl_ontology_subject(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology._namespace == EX

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
    def test_short_id_is_expanded(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology._expand_id("shapefile") == EX + "shapefile"

    @pytest.mark.parametrize("iri", ["http://other.org/fmt", "https://other.org/fmt"])
    def test_full_iri_is_unchanged(self, toy_ontology: FormatOntology, iri: str) -> None:
        assert toy_ontology._expand_id(iri) == iri

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


class TestIsDefined:
    def test_defined_format(self, edam_ontology: FormatOntology) -> None:
        assert edam_ontology.is_defined("format_4119") is True

    def test_defined_format_full_iri(self, edam_ontology: FormatOntology) -> None:
        assert edam_ontology.is_defined("http://edamontology.org/format_4119") is True

    def test_undefined_format(self, edam_ontology: FormatOntology) -> None:
        assert edam_ontology.is_defined("format_99999") is False

    def test_rdfs_class_is_defined(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_defined("rdfs_only") is True

    def test_only_referenced_as_object_is_undefined(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_defined("undeclared") is False


class TestIsSubclass:
    def test_identity(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("vector", "vector") is True

    def test_identity_holds_for_undefined_format(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("nonexistent", "nonexistent") is True

    def test_short_id_and_full_iri_are_identical(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("vector", EX + "vector") is True

    def test_direct_subclass(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("shapefile", "vector") is True

    def test_transitive_subclass(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("zipped_shapefile", "vector") is True

    def test_superclass_is_not_subclass(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("vector", "shapefile") is False

    def test_unrelated(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("geotiff", "vector") is False

    def test_equivalent_class_forward(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("tiff", "geotiff") is True

    def test_equivalent_class_backward(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("geotiff", "tiff") is True

    def test_subclass_via_equivalent_class(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("tiff", "raster") is True

    def test_cycle_terminates(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("cyc_a", "vector") is False

    def test_cycle_members_are_mutual_subclasses(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.is_subclass("cyc_a", "cyc_b") is True
        assert toy_ontology.is_subclass("cyc_b", "cyc_a") is True


class TestAreCompatible:
    def test_actual_subclass_of_expected(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.are_compatible(expected="vector", actual="shapefile") is True

    def test_actual_superclass_of_expected(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.are_compatible(expected="shapefile", actual="vector") is False


class TestIntrospection:
    def test_label(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.get_label("shapefile") == "Shapefile"

    def test_label_missing(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.get_label("vector") is None

    def test_comment(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.get_comment("shapefile") == "Composite vector format."

    def test_comment_missing(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.get_comment("vector") is None

    def test_values(self, toy_ontology: FormatOntology) -> None:
        values = toy_ontology.get_values("shapefile", EX + "file_extension")
        assert sorted(values) == ["dbf", "shp", "shx"]

    def test_values_missing(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.get_values("vector", EX + "file_extension") == []

    def test_parents(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.get_parents("shapefile") == [EX + "vector"]

    def test_parents_are_direct_only(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.get_parents("zipped_shapefile") == [EX + "shapefile"]

    def test_children(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.get_children("vector") == [EX + "shapefile"]

    def test_children_missing(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.get_children("zipped_shapefile") == []

    def test_equivalents_both_directions(self, toy_ontology: FormatOntology) -> None:
        assert toy_ontology.get_equivalents("tiff") == [EX + "geotiff"]
        assert toy_ontology.get_equivalents("geotiff") == [EX + "tiff"]
