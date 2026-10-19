"""Unit tests for the ``HTTPValidationResponseHandler``."""

from pathlib import Path

import pytest
from format_validator import (
    Cause,
    Error,
    FileInput,
    FormatIdentifier,
    Info,
    ValidationMode,
    ValidationRequest,
    ValidationResult,
    Warning,
)

from adapter.response_handler import HTTPValidationResponseHandler
from api.schemas.validation import FileFormatValidationEvent


@pytest.fixture
def request_(tmp_path: Path) -> ValidationRequest:
    return ValidationRequest(
        format_identifier=FormatIdentifier.GEOJSON,
        actual_file=FileInput(tmp_path / "sample.geojson"),
        mode=ValidationMode.BASIC,
    )


@pytest.fixture
def handler() -> HTTPValidationResponseHandler:
    return HTTPValidationResponseHandler()


class TestStatus:
    def test_success(self, handler: HTTPValidationResponseHandler, request_: ValidationRequest) -> None:
        response = handler.handle_success(ValidationResult.success(request_, Info("ok")))
        assert response.status == "SUCCESS"

    def test_failure(self, handler: HTTPValidationResponseHandler, request_: ValidationRequest) -> None:
        response = handler.handle_failure(ValidationResult.failure(request_, Error("broken")))
        assert response.status == "FAILURE"

    def test_uncertain(self, handler: HTTPValidationResponseHandler, request_: ValidationRequest) -> None:
        response = handler.handle_uncertain(ValidationResult.uncertain(request_, Warning("unsure")))
        assert response.status == "UNCERTAIN"


class TestEvents:
    def test_events_are_split_by_severity(
        self, handler: HTTPValidationResponseHandler, request_: ValidationRequest
    ) -> None:
        result = ValidationResult.uncertain(request_, Warning("unsure"))
        result.add(Info("note"))
        response = handler.handle_uncertain(result)
        assert [e.message for e in response.warnings] == ["unsure"]
        assert [e.message for e in response.infos] == ["note"]
        assert response.errors == []
        assert all(isinstance(e, FileFormatValidationEvent) for e in response.warnings + response.infos)

    def test_event_fields(self, handler: HTTPValidationResponseHandler, request_: ValidationRequest) -> None:
        error = Error("broken", cause=Cause.STRUCTURAL_MALFORMED)
        response = handler.handle_failure(ValidationResult.failure(request_, error))
        (event,) = response.errors
        assert event.message == "broken"
        assert event.severity == error.severity().value
        assert event.cause == Cause.STRUCTURAL_MALFORMED.value
        assert event.timestamp == error.timestamp.isoformat()

    def test_handlers_map_identically(
        self, handler: HTTPValidationResponseHandler, request_: ValidationRequest
    ) -> None:
        result = ValidationResult.failure(request_, Error("broken"))
        responses = [
            handler.handle_success(result),
            handler.handle_failure(result),
            handler.handle_uncertain(result),
        ]
        assert responses[0] == responses[1] == responses[2]
