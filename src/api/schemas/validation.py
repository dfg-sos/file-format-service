"""Pydantic schemas for the ``/validate`` endpoint."""

from typing import Literal

from pydantic import BaseModel, Field


class FileFormatValidationRequest(BaseModel):
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
        description="Validation mode: basic, structural, or full.",
    )
    expected_crs: str | None = Field(
        default=None,
        description=(
            "Expected coordinate reference system for FULL-mode metadata "
            "validation, in any form accepted by pyproj (e.g. 'EPSG:4326', a "
            "WKT string, or a proj4 string). Only checked in FULL mode."
        ),
    )
    expected_geometry_type: str | None = Field(
        default=None,
        description=(
            "Expected GeoJSON-style geometry type for FULL-mode metadata "
            "validation (e.g. 'Point', 'MultiPolygon'), matched "
            "case-insensitively. Only applies to vector formats and only "
            "checked in FULL mode. Unrecognized names make the result "
            "UNCERTAIN."
        ),
    )


class LocalValidationRequest(FileFormatValidationRequest):
    """JSON body for validating a file on storage shared with the service.

    Paths are given as the client sees them and must lie inside one of the
    directories configured in ``SOS_FFS_SHARED_DIRS``.
    """

    file_path: str = Field(
        ...,
        description="Absolute path of the file to validate. For multi-file formats, the primary file (e.g. the .shp).",
    )
    secondary_file_paths: list[str] = Field(
        default_factory=list,
        description=(
            "Absolute paths of the remaining files of a multi-file format (e.g. .shx, .dbf, .prj). "
            "They must be in the same directory as file_path."
        ),
    )


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
