"""Ontology-based format compatibility checker.

Uses ``rdflib`` to parse OWL/RDF ontologies and check ``rdfs:subClassOf``
relationships between format identifiers.

The implementation follows the same recursive pattern used by
``cwl_utils.file_formats.formatSubclassOf``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Set

from rdflib import Graph, OWL, RDFS, URIRef

logger = logging.getLogger(__name__)


def _expand_id(fmt: str) -> str:
    EDAM_NAMESPACE = "http://edamontology.org/"
    """Expand a short format identifier to a full URI if needed.

    If ``fmt`` does not start with ``http://`` or ``https://``, it is
    prefixed with the default EDAM namespace.
    """
    if fmt.startswith("http://") or fmt.startswith("https://"):
        return fmt
    return EDAM_NAMESPACE + fmt


class FormatOntology:
    """Wraps an OWL/RDF ontology and provides format compatibility queries."""

    def __init__(self, ontology_source: Optional[str | Path] = None):
        """Load an ontology.

        Args:
            ontology_source: Path to a local ``.owl`` file or a resolvable URI.
                             If ``None``, the ontology is empty (only identity checks work).
        """
        self.graph = Graph()
        if ontology_source is not None:
            try:
                self.graph.parse(str(ontology_source))
                logger.debug("Loaded ontology from %s", ontology_source)
            except Exception as exc:
                logger.warning("Could not load ontology from %s: %s", ontology_source, exc)
                raise

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
        fmt_uri = URIRef(_expand_id(fmt))
        cls_uri = URIRef(_expand_id(cls))

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
        fmt_uri = URIRef(_expand_id(fmt))
        parents = []
        for _s, _p, o in self.graph.triples((fmt_uri, RDFS.subClassOf, None)):
            parents.append(str(o))
        return parents

    def get_equivalents(self, fmt: str) -> list[str]:
        """Return all equivalent classes of ``fmt``."""
        fmt_uri = URIRef(_expand_id(fmt))
        eqs = []
        for _s, _p, o in self.graph.triples((fmt_uri, OWL.equivalentClass, None)):
            eqs.append(str(o))
        for s, _p, _o in self.graph.triples((None, OWL.equivalentClass, fmt_uri)):
            eqs.append(str(s))
        return eqs
