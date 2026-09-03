"""HTTP-specific ValidationResponseHandler implementation.

Translates ``format_validator.ValidationResult`` into Pydantic response
models suitable for FastAPI JSON responses.
"""

from format_validator import (
    ValidationResponseHandler,
    ValidationResult,
)

from api.schemas.validation import FileFormatValidationEvent, FileFormatValidationResponse


class HTTPValidationResponseHandler(ValidationResponseHandler):
    """Handles validation results and returns HTTP-friendly response models."""

    def handle_success(self, validation_result: ValidationResult) -> FileFormatValidationResponse:
        return self._to_response(validation_result)

    def handle_failure(self, validation_result: ValidationResult) -> FileFormatValidationResponse:
        return self._to_response(validation_result)

    def handle_uncertain(self, validation_result: ValidationResult) -> FileFormatValidationResponse:
        return self._to_response(validation_result)

    @staticmethod
    def _to_response(validation_result: ValidationResult) -> FileFormatValidationResponse:
        """Convert a ``ValidationResult`` into a ``ValidationResponse``."""
        data = validation_result.to_dict()

        return FileFormatValidationResponse(
            status=data["status"],
            errors=[FileFormatValidationEvent(**e) for e in data["errors"]],
            warnings=[FileFormatValidationEvent(**e) for e in data["warnings"]],
            infos=[FileFormatValidationEvent(**e) for e in data["infos"]],
        )
