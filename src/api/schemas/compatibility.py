"""Pydantic schemas for the ``/compatibility`` endpoint."""

from pydantic import BaseModel, Field


class CompatibilityRequest(BaseModel):
    """Request body for checking format compatibility."""

    expected_format: str = Field(..., description="The required / expected format identifier.")
    actual_format: str = Field(..., description="The provided / actual format identifier.")
    ontology_uri: str = Field(
        default="http://edamontology.org",
        description="Ontology URI that defines the format identifiers.",
    )


class CompatibilityResponse(BaseModel):
    """Response returned by the compatibility endpoint."""

    compatible: bool
    expected: str
    actual: str
    message: str
    ontology_source: str | None = None
