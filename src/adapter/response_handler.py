"""HTTP-specific ValidationResponseHandler implementation.

Translates ``format_validator.ValidationResult`` into Pydantic response
models suitable for FastAPI JSON responses.
"""

from format_validator import (
    ValidationResponseHandler,
    ValidationResult,
    ValidationStatus,
)

from api.schemas.validation import ValidationEvent, ValidationResponse


class HTTPValidationResponseHandler(ValidationResponseHandler):
    """Handles validation results and returns HTTP-friendly response models."""

    def handle_success(self, validation_result: ValidationResult) -> ValidationResponse:
        return self._to_response(validation_result)

    def handle_failure(self, validation_result: ValidationResult) -> ValidationResponse:
        return self._to_response(validation_result)

    def handle_uncertain(self, validation_result: ValidationResult) -> ValidationResponse:
        return self._to_response(validation_result)

    @staticmethod
    def _to_response(validation_result: ValidationResult) -> ValidationResponse:
        """Convert a ``ValidationResult`` into a ``ValidationResponse``."""
        data = validation_result.to_dict()
        valid = validation_result.status == ValidationStatus.SUCCESS

        return ValidationResponse(
            status=data["status"],
            valid=valid,
            errors=[ValidationEvent(**e) for e in data["errors"]],
            warnings=[ValidationEvent(**e) for e in data["warnings"]],
            infos=[ValidationEvent(**e) for e in data["infos"]],
        )
