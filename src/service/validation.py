"""Build validator requests for formats identified in an ontology."""

from collections.abc import Mapping
from pathlib import Path

from format_validator import (
    FileInput,
    FormatTranslator,
    InvalidRequest,
    MultiFileInput,
    ValidationMode,
    ValidationRequest,
    build_request,
)


class UnmappedFormat(InvalidRequest):
    """The format identifier has no mapping for the ontology namespace."""


def file_input(primary: Path, secondary: set[Path]) -> FileInput:
    """The validator's input for a primary file and the other files of a multi-file format."""
    return MultiFileInput(primary, secondary) if secondary else FileInput(primary)


def build_validation_request(
    ontology_namespace: str,
    format_identifier: str,
    mode: ValidationMode,
    files: FileInput,
    translator: FormatTranslator,
    expected_metadata: Mapping[str, str] | None = None,
) -> ValidationRequest:
    """Build the validator's request for a format of an ontology; the files are not read.

    Raises:
        UnmappedFormat: The format has no mapping for the ontology namespace.
        InvalidRequest: The format has no validator, or ``expected_metadata``
            has keys or values the format's validator does not support.
    """
    format_id = translator.to_local(ontology_namespace + format_identifier)
    if format_id is None:
        raise UnmappedFormat(
            f"Format identifier '{format_identifier}' not supported for ontology namespace '{ontology_namespace}'"
        )
    return build_request(format_id, files, mode, expected_metadata)
