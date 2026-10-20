"""FastAPI dependency-injection wiring.

Provides singleton instances of settings, services, and utilities so that
routers can receive them via ``Depends`` without manual construction.
"""

from functools import lru_cache
from pathlib import Path

from fastapi import Depends, Form, HTTPException
from format_validator import FormatTranslator

from api.schemas.validation import FileFormatValidationRequest
from config import Settings
from core import FormatOntology
from service.ontology_registry import OntologyRegistry
from service.shared_paths import SharedPathResolver


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
def get_shared_path_resolver() -> SharedPathResolver:
    """Return cached ``SharedPathResolver`` for the configured shared directories."""
    return SharedPathResolver(get_settings().shared_dirs)


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


def check_formats_defined(
    ontology: FormatOntology,
    ontology_schema_url: str,
    formats: list[str],
    status_code: int,
) -> None:
    """Verify that every format is defined as a class in the ontology.

    Raises ``HTTPException`` with ``status_code`` listing the undefined formats
    as expanded IRIs, so the client can see which namespace was assumed.
    """
    unknown = sorted({ontology._expand_id(fmt) for fmt in formats if not ontology.is_defined(fmt)})
    if unknown:
        raise HTTPException(
            status_code=status_code,
            detail={
                "message": f"Format(s) not defined in ontology {ontology_schema_url}",
                "unknown_formats": unknown,
            },
        )


def get_validation_request(
    ontology_namespace: str = Form(
        ..., description="Ontology namespace (base URI) that defines the format identifier."
    ),
    format_identifier: str = Form(
        ..., description="Format identifier in the given ontology (e.g. format_4119)."
    ),
    mode: str = Form(
        default="basic",
        description="Validation mode: basic, structural, or full.",
    ),
    expected_crs: str | None = Form(
        default=None,
        description="Expected CRS for FULL-mode validation (any pyproj-recognized string).",
    ),
    expected_geometry_type: str | None = Form(
        default=None,
        description="Expected GeoJSON-style geometry type for FULL-mode validation on vector formats.",
    ),
) -> FileFormatValidationRequest:
    """Group multipart form fields into a ``FileFormatValidationRequest`` DTO."""
    return FileFormatValidationRequest(
        ontology_namespace=ontology_namespace,
        format_identifier=format_identifier,
        mode=mode,
        expected_crs=expected_crs,
        expected_geometry_type=expected_geometry_type,
    )


def get_file_storage_path() -> Path:
    """Return the directory where uploaded files are temporarily stored.

    In production this could be backed by S3 / volume mounts.
    """
    return Path("/tmp/sos_file_format_service/uploads")
