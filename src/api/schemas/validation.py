"""Pydantic schemas for the ``/validate`` endpoint."""

from typing import Literal

from pydantic import BaseModel, Field


class ValidationRequestSchema(BaseModel):
    """Request body for the file validation endpoint.

    These fields are sent as multipart form data alongside the uploaded file.
    """

    ontology_namespace: str = Field(
        ...,
        description="Ontology namespace (base URI) that defines the format identifier.",
    )
    format_identifier: str = Field(
        ...,
        description="Format identifier in the given ontology (e.g. format_4119).",
    )
    mode: str = Field(
        default="basic",
        description="Validation mode: basic, structural, crs, or full.",
    )


class ValidationEvent(BaseModel):
    """A single event (error, warning, or info) emitted during validation."""

    message: str
    timestamp: str
    severity: str
    cause: str | None = None


class ValidationResponse(BaseModel):
    """Response returned by the validation endpoint.

    The ``status`` field carries the exact validation outcome:
    ``SUCCESS``, ``UNCERTAIN``, or ``FAILURE``.
    """

    status: Literal["SUCCESS", "UNCERTAIN", "FAILURE"]
    errors: list[ValidationEvent]
    warnings: list[ValidationEvent]
    infos: list[ValidationEvent]
