"""Business-layer service for ontology-based format compatibility checks."""

from compatibility import CompatibilityResult, FormatOntology


class CompatibilityService:
    """Provides format compatibility queries against a supplied ``FormatOntology``."""

    @staticmethod
    def check(expected: str, actual: str, ontology: FormatOntology) -> CompatibilityResult:
        """Check whether *actual* format is compatible with *expected* format.

        Args:
            expected: The required / expected format identifier.
            actual: The provided / actual format identifier.
            ontology: The ``FormatOntology`` instance to query.

        Returns:
            A ``CompatibilityResult`` with the outcome and a human-readable
            message.
        """
        compatible = ontology.are_compatible(expected, actual)
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
        )

    @staticmethod
    def get_parents(fmt: str, ontology: FormatOntology) -> list[str]:
        """Return all direct parent classes of ``fmt`` according to the ontology."""
        return ontology.get_parents(fmt)

    @staticmethod
    def get_equivalents(fmt: str, ontology: FormatOntology) -> list[str]:
        """Return all equivalent classes of ``fmt`` according to the ontology."""
        return ontology.get_equivalents(fmt)
