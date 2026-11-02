"""FastAPI dependency-injection wiring.

Provides singleton instances of settings, services, and utilities so that
routers can receive them via ``Depends`` without manual construction.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, Form, HTTPException, status
from format_validator import FormatTranslator
from pydantic import ValidationError

from api.schemas.validation import FileFormatValidationRequest, MetadataValidationRequest
from config import MAPPINGS_DIR, Settings
from core import FormatOntology
from service.ontology_registry import OntologyRegistry
from service.shared_paths import SharedPathResolver

logger = logging.getLogger(__name__)


@lru_cache
def get_settings() -> Settings:
    """Return cached service settings."""
    return Settings()


def load_format_translator(mappings_dir: Path) -> FormatTranslator:
    """Load the mapping files (``*.json``) in ``mappings_dir`` into one translator.

    Each file maps the format identifiers of the ontology ``ontology_uri`` to
    validator format identifiers. The translator is keyed by the full format
    IRI, ``ontology_uri`` followed by the identifier. A missing or empty
    directory yields a translator without mappings, which rejects every
    format; this is logged as a warning.

    Raises:
        ValueError: Two files map the same IRI to different formats, or a
            file maps to a format identifier the validator does not know.
    """
    translator = FormatTranslator({})
    namespaces = []
    for path in sorted(mappings_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        namespace = data["ontology_uri"]
        namespaces.append(namespace)
        try:
            translator |= FormatTranslator({namespace + identifier: fid for identifier, fid in data["mappings"].items()})
        except ValueError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
    if namespaces:
        logger.info("Loaded format mappings for ontologies: %s", namespaces)
    else:
        logger.warning("No mapping files (*.json) found in %s, validation rejects every format", mappings_dir)
    return translator


@lru_cache
def get_format_translator() -> FormatTranslator:
    """Return cached ``FormatTranslator`` with the mappings in ``MAPPINGS_DIR``."""
    return load_format_translator(MAPPINGS_DIR)


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


def get_upload_request(
    ontology_namespace: str = Form(
        ..., description="Ontology namespace (base URI) that defines the format identifier."
    ),
    format_identifier: str = Form(
        ..., description="Format identifier in the given ontology (e.g. format_4119)."
    ),
) -> FileFormatValidationRequest:
    """Group multipart form fields into a ``FileFormatValidationRequest``."""
    return FileFormatValidationRequest(ontology_namespace=ontology_namespace, format_identifier=format_identifier)


def get_metadata_upload_request(
    request: FileFormatValidationRequest = Depends(get_upload_request),
    expected_metadata: str | None = Form(
        default=None,
        description=(
            'Expected metadata as a JSON object, e.g. {"crs": "EPSG:4326"}. '
            "The supported keys depend on the validator of the format."
        ),
    ),
) -> MetadataValidationRequest:
    """Group multipart form fields into a ``MetadataValidationRequest``.

    Raises ``HTTPException`` (422) when ``expected_metadata`` is not a JSON
    object of strings.
    """
    try:
        return MetadataValidationRequest(
            **request.model_dump(),
            expected_metadata=json.loads(expected_metadata) if expected_metadata else {},
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"expected_metadata must be a JSON object of strings: {exc}",
        ) from exc


def get_file_storage_path() -> Path:
    """Return the directory where uploaded files are temporarily stored.

    In production this could be backed by S3 / volume mounts.
    """
    return Path("/tmp/sos_file_format_service/uploads")
