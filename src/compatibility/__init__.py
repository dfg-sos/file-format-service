"""Format compatibility checker subpackage.

Provides ontology-based checking of whether two format identifiers are
compatible (e.g. whether ``shapefile`` is compatible with ``vector``).
"""

from .ontology import FormatOntology
from .result import CompatibilityResult

__all__ = ["FormatOntology", "CompatibilityResult"]
