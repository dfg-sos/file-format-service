"""Shared Pydantic schemas used across multiple endpoint modules."""

from pydantic import BaseModel


class HTTPError(BaseModel):
    """Standard error response body."""

    detail: str


class FormatInfo(BaseModel):
    """Information about a supported format mapping."""

    ontology_uri: str
    format_identifier: str
    validator_format: str
