"""Result type for format compatibility checks."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CompatibilityResult:
    """Result of checking whether two format identifiers are compatible.

    Attributes:
        compatible: ``True`` if the actual format can be used where the expected format is required.
        expected: The expected (required) format identifier that was checked.
        actual: The actual format identifier that was checked.
        message: Human-readable explanation of the result.
        ontology_source: The ontology source (URI or file path) used for the check.
    """

    compatible: bool
    expected: str
    actual: str
    message: str
    ontology_source: Optional[str] = None

    def __bool__(self) -> bool:
        return self.compatible
