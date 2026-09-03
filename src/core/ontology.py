"""Ontology-based format compatibility checker.

Uses ``rdflib`` to parse OWL/RDF ontologies and check ``rdfs:subClassOf``
relationships between format identifiers.

The implementation follows the same recursive pattern used by
``cwl_utils.file_formats.formatSubclassOf``.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Optional, Set

from rdflib import Graph, OWL, RDFS, RDF, URIRef

logger = logging.getLogger(__name__)


class FormatOntology:
    """Wraps an OWL/RDF ontology and provides format compatibility queries."""

    def __init__(self, graph: Graph, namespace: Optional[str] = None):
        """Wrap an already parsed RDF graph.

        Args:
            graph: Pre-populated ``rdflib.Graph``.
            namespace: The ontology namespace used to expand short format IDs.
                If ``None``, it is inferred from the graph where possible.
        """
        self.graph = graph
        self._namespace = namespace or self._infer_namespace()

    @classmethod
    def from_source(cls, ontology_source: str | Path) -> "FormatOntology":
        """Load an ontology from a local file path or a resolvable URI.

        Args:
            ontology_source: Path to a local ``.owl`` file or a resolvable URI.

        Returns:
            A populated ``FormatOntology`` instance.
        """
        graph = Graph()
        try:
            graph.parse(str(ontology_source))
            logger.debug("Loaded ontology from %s", ontology_source)
        except Exception as exc:
            logger.warning("Could not load ontology from %s: %s", ontology_source, exc)
            raise
        return cls(graph=graph)

    @classmethod
    def from_bytes(cls, data: bytes, format: Optional[str] = None) -> "FormatOntology":
        """Parse an ontology from raw bytes.

        Args:
            data: Raw RDF/OWL content.
            format: RDF serialisation format (e.g. ``"xml"``, ``"turtle"``).
                If ``None``, ``rdflib`` attempts to auto-detect.

        Returns:
            A populated ``FormatOntology`` instance.
        """
        graph = Graph()
        try:
            graph.parse(data=data, format=format)
        except Exception as exc:
            logger.warning("Could not parse ontology from bytes: %s", exc)
            raise
        return cls(graph=graph)

    def _infer_namespace(self) -> Optional[str]:
        """Attempt to infer the ontology namespace from the graph.

        The primary strategy is to look for the ``owl:Ontology`` subject.
        If that yields nothing, we fall back to the most common prefix among
        ``owl:Class`` subjects.
        """
        # Strategy 1: owl:Ontology subject
        for subject in self.graph.subjects(RDF.type, OWL.Ontology):
            return str(subject)

        # Strategy 2: most common prefix among owl:Class subjects
        prefixes: Counter = Counter()
        for subject in self.graph.subjects(RDF.type, OWL.Class):
            uri = str(subject)
            for sep in ("#", "/"):
                if sep in uri:
                    prefix = uri.rsplit(sep, 1)[0] + sep
                    prefixes[prefix] += 1
                    break

        if prefixes:
            return prefixes.most_common(1)[0][0]

        return None

    def _expand_id(self, fmt: str) -> str:
        """Expand a short format identifier to a full URI using the inferred namespace.

        If ``fmt`` already starts with ``http://`` or ``https://`` it is
        returned unchanged. Otherwise it is prefixed with the ontology
        namespace (if one was inferred).
        """
        if fmt.startswith("http://") or fmt.startswith("https://"):
            return fmt
        if self._namespace:
            return self._namespace.rstrip("/") + "/" + fmt
        return fmt

    # ------------------------------------------------------------------
    # Core logic (mirrors cwl-utils formatSubclassOf)
    # ------------------------------------------------------------------

    def is_subclass(self, fmt: str, cls: str, visited: Optional[Set[str]] = None) -> bool:
        """Check if ``fmt`` is a subclass of ``cls`` (direct or transitive).

        Also considers ``owl:equivalentClass`` in both directions.

        Args:
            fmt: The format identifier to test (short name or full URI).
            cls: The target class to test against (short name or full URI).
            visited: Internal set for cycle detection.

        Returns:
            ``True`` if ``fmt`` is the same as, or a subclass of, ``cls``.
        """
        fmt_uri = URIRef(self._expand_id(fmt))
        cls_uri = URIRef(self._expand_id(cls))

        if fmt_uri == cls_uri:
            return True

        if visited is None:
            visited = set()

        fmt_str = str(fmt_uri)
        if fmt_str in visited:
            return False
        visited.add(fmt_str)

        # Follow rdfs:subClassOf upward
        for _s, _p, o in self.graph.triples((fmt_uri, RDFS.subClassOf, None)):
            if self.is_subclass(str(o), cls, visited):
                return True

        # Follow owl:equivalentClass in both directions
        for _s, _p, o in self.graph.triples((fmt_uri, OWL.equivalentClass, None)):
            if self.is_subclass(str(o), cls, visited):
                return True
        for s, _p, _o in self.graph.triples((None, OWL.equivalentClass, fmt_uri)):
            if self.is_subclass(str(s), cls, visited):
                return True

        return False

    def are_compatible(self, expected: str, actual: str) -> bool:
        """Check compatibility in a **directional** sense.

        Returns ``True`` when the *actual* format is the same as, or a
        subclass of, the *expected* format.

        Args:
            expected: The format that is required / expected.
            actual:   The format that is available / provided.

        Returns:
            ``True`` if ``actual`` satisfies the ``expected`` requirement.
        """
        return self.is_subclass(actual, expected)

    def get_parents(self, fmt: str) -> list[str]:
        """Return all direct parent classes of ``fmt``."""
        fmt_uri = URIRef(self._expand_id(fmt))
        parents = []
        for _s, _p, o in self.graph.triples((fmt_uri, RDFS.subClassOf, None)):
            parents.append(str(o))
        return parents

    # ------------------------------------------------------------------
    # Format introspection helpers
    # ------------------------------------------------------------------

    def get_label(self, fmt: str) -> Optional[str]:
        """Return the ``rdfs:label`` of ``fmt``, if any."""
        fmt_uri = URIRef(self._expand_id(fmt))
        for _s, _p, o in self.graph.triples((fmt_uri, RDFS.label, None)):
            return str(o)
        return None

    def get_comment(self, fmt: str) -> Optional[str]:
        """Return the ``rdfs:comment`` of ``fmt``, if any."""
        fmt_uri = URIRef(self._expand_id(fmt))
        for _s, _p, o in self.graph.triples((fmt_uri, RDFS.comment, None)):
            return str(o)
        return None

    def get_children(self, fmt: str) -> list[str]:
        """Return all direct child classes of ``fmt``.

        Children are classes that have ``fmt`` as a ``rdfs:subClassOf``.
        """
        fmt_uri = URIRef(self._expand_id(fmt))
        children = []
        for s, _p, _o in self.graph.triples((None, RDFS.subClassOf, fmt_uri)):
            children.append(str(s))
        return children

    def get_values(self, fmt: str, predicate: str) -> list[str]:
        """Return all values for an arbitrary predicate URI.

        Args:
            fmt: The format identifier (short or full URI).
            predicate: Full predicate URI (e.g. ``"http://edamontology.org/file_extension"``).

        Returns:
            List of matching values as strings.
        """
        fmt_uri = URIRef(self._expand_id(fmt))
        pred_uri = URIRef(predicate)
        values = []
        for _s, _p, o in self.graph.triples((fmt_uri, pred_uri, None)):
            values.append(str(o))
        return values

    def get_equivalents(self, fmt: str) -> list[str]:
        """Return all equivalent classes of ``fmt``."""
        fmt_uri = URIRef(self._expand_id(fmt))
        eqs = []
        for _s, _p, o in self.graph.triples((fmt_uri, OWL.equivalentClass, None)):
            eqs.append(str(o))
        for s, _p, _o in self.graph.triples((None, OWL.equivalentClass, fmt_uri)):
            eqs.append(str(s))
        return eqs
