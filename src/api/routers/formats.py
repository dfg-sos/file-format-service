"""FastAPI router for the ``/formats`` endpoint.

Lists all supported format mappings and provides ontology introspection.
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_compatibility_service, get_settings
from api.schemas.common import FormatInfo
from config import Settings
from service.compatibility_service import CompatibilityService

router = APIRouter(tags=["formats"])


def _load_mappings(settings: Settings) -> list[dict[str, str]]:
    """Read JSON mapping files for introspection."""
    results: list[dict[str, str]] = []
    for mapping_file in sorted(settings.mappings_dir.glob("*.json")):
        try:
            with open(mapping_file, encoding="utf-8") as fh:
                data = json.load(fh)
            uri = data.get("ontology_uri", "")
            for fmt_id, val_fmt in data.get("mappings", {}).items():
                results.append(
                    {
                        "ontology_uri": uri,
                        "format_identifier": fmt_id,
                        "validator_format": val_fmt,
                    }
                )
        except (json.JSONDecodeError, OSError):
            continue
    return results


@router.get(
    "/formats",
    response_model=list[FormatInfo],
    summary="List supported format mappings",
)
async def list_formats(
    ontology_uri: str | None = Query(
        None, description="Filter by ontology URI."
    ),
    settings: Settings = Depends(get_settings),
) -> list[FormatInfo]:
    """Return all format identifier mappings known to the service.

    Each entry maps an ontology-specific format identifier to the internal
    validator format name.
    """
    mappings = _load_mappings(settings)
    if ontology_uri:
        mappings = [m for m in mappings if m["ontology_uri"] == ontology_uri]
    return [FormatInfo(**m) for m in mappings]


@router.get(
    "/formats/{format_id}/parents",
    response_model=list[str],
    summary="List parent formats of a given format",
)
async def get_format_parents(
    format_id: str,
    service: CompatibilityService = Depends(get_compatibility_service),
) -> list[str]:
    """Return the direct parent classes of ``format_id`` according to the ontology."""
    return service.get_parents(format_id)


@router.get(
    "/formats/{format_id}/equivalents",
    response_model=list[str],
    summary="List equivalent formats of a given format",
)
async def get_format_equivalents(
    format_id: str,
    service: CompatibilityService = Depends(get_compatibility_service),
) -> list[str]:
    """Return the equivalent classes of ``format_id`` according to the ontology."""
    return service.get_equivalents(format_id)
