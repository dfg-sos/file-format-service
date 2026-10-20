"""Pydantic schemas for the ``/format-info`` endpoint."""

from pydantic import BaseModel, Field


class FormatInfoRequest(BaseModel):
    """Request body for querying format information."""

    ontology_schema_url: str = Field(
        ...,
        description="URL to the OWL/RDF ontology schema file.",
    )
    format_identifier: str = Field(
        ...,
        description="Format identifier in the ontology (e.g. format_4119).",
    )


class FormatInfoResponse(BaseModel):
    """Response containing detailed information about a format."""

    format_uri: str = Field(..., description="Full URI of the format in the ontology.")
    label: str | None = Field(None, description="Human-readable label (rdfs:label).")
    comment: str | None = Field(None, description="Description (rdfs:comment).")
    parents: list[str] = Field(default_factory=list, description="Direct parent classes.")
    children: list[str] = Field(default_factory=list, description="Direct child classes.")
    equivalents: list[str] = Field(default_factory=list, description="Equivalent classes.")
    see_also: list[str] = Field(
        default_factory=list, description="Related links (rdfs:seeAlso, if present)."
    )
    annotations: dict[str, list[str]] = Field(
        default_factory=dict,
        description="All annotations of the class, keyed by predicate IRI (ontology-agnostic).",
    )
