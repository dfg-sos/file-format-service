"""Pydantic schemas for the ``/validate`` endpoint."""

from typing import Literal

from pydantic import BaseModel, Field


class FileFormatValidationRequest(BaseModel):
    """Fields common to all validation endpoints."""

    ontology_namespace: str = Field(
        ...,
        description="Ontology namespace (base URI) that defines the format identifier.",
    )
    format_identifier: str = Field(
        ...,
        description="Format identifier in the given ontology (e.g. format_4119).",
    )


class FullValidationRequest(FileFormatValidationRequest):
    """Request for full validation, which also checks the file's metadata."""

    expected_metadata: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Expected metadata of the file, as key/value pairs. The supported keys "
            "depend on the validator of the format (e.g. 'crs' and 'geometry_type' "
            "for vector formats); other keys are rejected. A key that is omitted or "
            "empty skips that check, a value that cannot be parsed makes the result "
            "UNCERTAIN."
        ),
    )


class PathValidationRequest(FileFormatValidationRequest):
    """JSON body that references the file by path instead of uploading it."""

    file_path: str = Field(
        ...,
        description="Path of the file to validate. For multi-file formats, the primary file (e.g. the .shp).",
    )
    secondary_file_paths: list[str] = Field(
        default_factory=list,
        description=(
            "Paths of the remaining files of a multi-file format (e.g. .shx, .dbf, .prj). "
            "They must be in the same directory as file_path."
        ),
    )


class FullPathValidationRequest(PathValidationRequest, FullValidationRequest):
    """JSON body for full validation of a file on shared storage."""


class FileFormatValidationEvent(BaseModel):
    """A single event (error, warning, or info) emitted during validation."""

    message: str
    timestamp: str
    severity: str
    cause: str | None = None


class FileFormatValidationResponse(BaseModel):
    """Response returned by the validation endpoint.

    The ``status`` field carries the exact validation outcome:
    ``SUCCESS``, ``UNCERTAIN``, or ``FAILURE``.
    """

    status: Literal["SUCCESS", "UNCERTAIN", "FAILURE"]
    errors: list[FileFormatValidationEvent]
    warnings: list[FileFormatValidationEvent]
    infos: list[FileFormatValidationEvent]
