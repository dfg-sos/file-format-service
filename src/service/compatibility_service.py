"""Business-layer service for ontology-based format compatibility checks."""

from pathlib import Path
from typing import Optional

from compatibility import CompatibilityResult, FormatOntology
from config import Settings


class CompatibilityService:
    """Wraps ``FormatOntology`` to provide format compatibility queries.

    Loads the ontology from the configured path and exposes a single
    ``check()`` method that returns a ``CompatibilityResult``.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._ontology: Optional[FormatOntology] = None
        self._load_ontology()

    def _load_ontology(self) -> None:
        """Load the OWL ontology from disk."""
        ontology_path = self.settings.ontology_path
        if ontology_path.exists():
            self._ontology = FormatOntology(ontology_path)
        else:
            self._ontology = FormatOntology(None)

    def check(
        self, expected: str, actual: str, ontology_source: Optional[str] = None
    ) -> CompatibilityResult:
        """Check whether *actual* format is compatible with *expected* format.

        Args:
            expected: The required / expected format identifier.
            actual: The provided / actual format identifier.
            ontology_source: Optional ontology source URI for the result.

        Returns:
            A ``CompatibilityResult`` with the outcome and a human-readable
            message.
        """
        if self._ontology is None:
            return CompatibilityResult(
                compatible=False,
                expected=expected,
                actual=actual,
                message="Ontology not loaded; cannot perform compatibility check.",
                ontology_source=ontology_source,
            )

        compatible = self._ontology.are_compatible(expected, actual)
        if compatible:
            message = (
                f"'{actual}' is compatible with '{expected}' "
                f"(same as, or subclass of, the expected format)."
            )
        else:
            message = (
                f"'{actual}' is **not** compatible with '{expected}' "
                f"(not the same format, and not a subclass)."
            )

        return CompatibilityResult(
            compatible=compatible,
            expected=expected,
            actual=actual,
            message=message,
            ontology_source=ontology_source or str(self.settings.ontology_path),
        )

    def get_parents(self, fmt: str) -> list[str]:
        """Return all direct parent classes of ``fmt`` according to the ontology."""
        if self._ontology is None:
            return []
        return self._ontology.get_parents(fmt)

    def get_equivalents(self, fmt: str) -> list[str]:
        """Return all equivalent classes of ``fmt`` according to the ontology."""
        if self._ontology is None:
            return []
        return self._ontology.get_equivalents(fmt)
