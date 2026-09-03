"""HTTP-specific ValidationRequestBuilder implementation.

Consumes an API-layer DTO and produces a ``format_validator.ValidationRequest``
by resolving the ontology format identifier via ``FormatTranslator``.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from format_validator import (
    FileInput,
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

        Returns ``None`` when the format identifier cannot be resolved
        (the orchestrator will surface this as an uncertain result).
        """
        format_id: Optional[FormatIdentifier] = self.translator.to_local(
            self.dto.format_identifier, self.dto.ontology_namespace
        )
        if format_id is None:
            return None

        file_input = FileInput(self.dto.file_path)

        return ValidationRequest(
            actual_file=file_input,
            format_identifier=format_id,
            mode=self.dto.mode,
        )
