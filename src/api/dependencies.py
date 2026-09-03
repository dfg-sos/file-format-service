"""FastAPI dependency-injection wiring.

Provides singleton instances of settings, services, and utilities so that
routers can receive them via ``Depends`` without manual construction.
"""

from functools import lru_cache
from pathlib import Path

from fastapi import Depends, Form

from api.schemas.validation import FileFormatValidationRequest
from compatibility import FormatOntology
from config import Settings
from format_validator import FormatTranslator
from service.ontology_registry import OntologyRegistry


@lru_cache
def get_settings() -> Settings:
    """Return cached service settings."""
    return Settings()


@lru_cache
def get_format_translator() -> FormatTranslator:
    """Return cached ``FormatTranslator`` loaded from the configured directory."""
    settings = get_settings()
    return FormatTranslator(settings.mappings_dir)


@lru_cache
def get_ontology_registry() -> OntologyRegistry:
    """Return cached ``OntologyRegistry`` for ontology fetch / caching."""
    return OntologyRegistry()


async def resolve_ontology(
    ontology_schema_url: str,
    registry: OntologyRegistry = Depends(get_ontology_registry),
) -> FormatOntology:
    """Resolve an ontology schema URL to a parsed ``FormatOntology``.

    Uses the registry's in-memory cache to avoid repeated fetches.
    """
    return await registry.resolve(ontology_schema_url)


def get_validation_request(
    ontology_namespace: str = Form(
        ..., description="Ontology namespace (base URI) that defines the format identifier."
    ),
    format_identifier: str = Form(
        ..., description="Format identifier in the given ontology (e.g. format_4119)."
    ),
    mode: str = Form(
        default="basic",
        description="Validation mode: basic, structural, crs, or full.",
    ),
) -> FileFormatValidationRequest:
    """Group multipart form fields into a ``FileFormatValidationRequest`` DTO."""
    return FileFormatValidationRequest(
        ontology_namespace=ontology_namespace,
        format_identifier=format_identifier,
        mode=mode,
    )


def get_file_storage_path() -> Path:
    """Return the directory where uploaded files are temporarily stored.

    In production this could be backed by S3 / volume mounts.
    """
    return Path("/tmp/sos_file_format_service/uploads")
