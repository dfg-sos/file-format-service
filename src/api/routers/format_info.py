"""FastAPI router for the ``/format-info`` endpoint.

Queries an ontology for detailed information about a given format identifier.
"""

import httpx
from fastapi import APIRouter, HTTPException, status

from api.dependencies import get_ontology_registry
from api.schemas.format_info import FormatInfoRequest, FormatInfoResponse
from core.ontology import FormatOntology
from rdflib import RDFS

router = APIRouter(tags=["format-info"])

# EDAM-specific predicate URIs (optional — will be empty for non-EDAM ontologies)
_EDAM_FILE_EXTENSION = "http://edamontology.org/file_extension"
_EDAM_MEDIA_TYPE = "http://edamontology.org/media_type"
_EDAM_DOCUMENTATION = "http://edamontology.org/documentation"


@router.post(
    "/format-info",
    response_model=FormatInfoResponse,
    summary="Get detailed information about a format",
    response_description="Format metadata including label, parents, children, etc.",
)
async def get_format_info(
    request: FormatInfoRequest,
) -> FormatInfoResponse:
    """Return detailed information about a format identifier from an ontology.

    The endpoint resolves the ontology schema, then queries the graph for
    labels, comments, parent/child relationships, equivalent classes, and
    optional ontology-specific metadata (file extensions, media type, etc.).
    """
    registry = get_ontology_registry()
    try:
        ontology = await registry.resolve(request.ontology_schema_url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch ontology schema: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ontology schema: {exc}",
        ) from exc

    return _build_response(request.format_identifier, ontology)


def _build_response(fmt: str, ontology: FormatOntology) -> FormatInfoResponse:
    """Assemble a ``FormatInfoResponse`` from ontology queries."""
    fmt_uri = ontology._expand_id(fmt)

    # Single-value optional fields
    label = ontology.get_label(fmt)
    comment = ontology.get_comment(fmt)
    media_type = _first_or_none(ontology.get_values(fmt, _EDAM_MEDIA_TYPE))

    # Multi-value lists
    parents = ontology.get_parents(fmt)
    children = ontology.get_children(fmt)
    equivalents = ontology.get_equivalents(fmt)
    file_extensions = ontology.get_values(fmt, _EDAM_FILE_EXTENSION)
    see_also = _query_values(ontology, fmt, RDFS.seeAlso)
    documentation = ontology.get_values(fmt, _EDAM_DOCUMENTATION)

    return FormatInfoResponse(
        format_uri=fmt_uri,
        label=label,
        comment=comment,
        parents=parents,
        children=children,
        equivalents=equivalents,
        file_extensions=file_extensions,
        media_type=media_type,
        see_also=see_also,
        documentation=documentation,
    )


def _first_or_none(values: list[str]) -> str | None:
    return values[0] if values else None


def _query_values(ontology: FormatOntology, fmt: str, predicate) -> list[str]:
    from rdflib import URIRef
    fmt_uri = URIRef(ontology._expand_id(fmt))
    values = []
    for _s, _p, o in ontology.graph.triples((fmt_uri, predicate, None)):
        values.append(str(o))
    return values
