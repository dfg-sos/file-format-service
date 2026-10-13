"""HTTP-specific ValidationRequestBuilder implementation.

Consumes an API-layer DTO and produces a ``format_validator.ValidationRequest``
by resolving the ontology format identifier via ``FormatTranslator``.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from format_validator import (
    EOMetadata,
    FileInput,
    MultiFileInput,
    FormatIdentifier,
    FormatTranslator,
    ValidationMode,
    ValidationRequest,
    ValidationRequestBuilder,
)


@dataclass
class ValidationRequestDTO:
    """Internal data transfer object for validation requests.

    Aggregates the fields received from the HTTP API so the builder does not
    need to depend on FastAPI / Pydantic types.
    """

    ontology_namespace: str
    format_identifier: str
    mode: ValidationMode
    file_path: Path
    secondary_file_paths: set[Path] = field(default_factory=set)
    expected_crs: Optional[str] = None
    expected_geometry_type: Optional[str] = None


class HTTPValidationRequestBuilder(ValidationRequestBuilder):
    """Builds a ``ValidationRequest`` from an HTTP API request DTO.

    Uses ``FormatTranslator`` to translate the ontology-specific format
    identifier into a ``FormatIdentifier`` understood by the validator module.
    """

    def __init__(self, dto: ValidationRequestDTO, translator: FormatTranslator):
        self.dto = dto
        self.translator = translator

    def build(self) -> Optional[ValidationRequest]:
        """Build and return a ``ValidationRequest``, or ``None`` on failure.

        Returns ``None`` when the format identifier cannot be resolved, or
        when the expected CRS / geometry type strings cannot be parsed into
        an ``EOMetadata`` sidecar (e.g. an invalid CRS string) — in both
        cases the orchestrator surfaces this as an uncertain result.
        """
        format_id: Optional[FormatIdentifier] = self.translator.to_local(
            self.dto.format_identifier, self.dto.ontology_namespace
        )
        if format_id is None:
            return None

        # ``EOMetadata.from_strings`` keeps CRS/geometry-type parsing (pyproj,
        # shapely) inside the format_validator package; catching broadly here
        # avoids this service needing to import pyproj just to name the
        # exception type it can raise.
        try:
            metadata = EOMetadata.from_strings(
                crs=self.dto.expected_crs,
                geometry_type=self.dto.expected_geometry_type,
            )
        except Exception:
            return None

        file_input: FileInput
        if self.dto.secondary_file_paths:
            file_input = MultiFileInput(self.dto.file_path, self.dto.secondary_file_paths)
        else:
            file_input = FileInput(self.dto.file_path)

        return ValidationRequest(
            actual_file=file_input,
            format_identifier=format_id,
            mode=self.dto.mode,
            metadata=metadata,
        )
