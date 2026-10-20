"""FastAPI router for the ``/format-info`` endpoint.

Queries an ontology for detailed information about a given format identifier.
"""

import httpx
from fastapi import APIRouter, HTTPException, status

from api.dependencies import check_formats_defined, get_ontology_registry
from api.schemas.format_info import FormatInfoRequest, FormatInfoResponse
from core.ontology import FormatOntology
from rdflib import RDFS

router = APIRouter(tags=["format-info"])


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
    all other annotations of the class (keyed by predicate IRI).

    Status codes:

    - ``200``: the format is defined; the body holds its metadata.
    - ``400``: the ontology schema could not be parsed.
    - ``404``: a local (``file://``) ontology schema does not exist, or the
      format is not defined in the ontology. In the latter case ``detail`` is
      ``{"message": ..., "unknown_formats": [<expanded IRI>]}``.
    - ``422``: the request body is invalid.
    - ``502``: the ontology schema could not be fetched.
    """
    registry = get_ontology_registry()
    try:
        ontology = await registry.resolve(request.ontology_schema_url)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
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

    check_formats_defined(
        ontology,
        request.ontology_schema_url,
        [request.format_identifier],
        status_code=status.HTTP_404_NOT_FOUND,
    )

    return _build_response(request.format_identifier, ontology)


def _build_response(fmt: str, ontology: FormatOntology) -> FormatInfoResponse:
    """Assemble a ``FormatInfoResponse`` from ontology queries."""
    return FormatInfoResponse(
        format_uri=ontology._expand_id(fmt),
        label=ontology.get_label(fmt),
        comment=ontology.get_comment(fmt),
        parents=ontology.get_parents(fmt),
        children=ontology.get_children(fmt),
        equivalents=ontology.get_equivalents(fmt),
        see_also=ontology.get_values(fmt, str(RDFS.seeAlso)),
        annotations=ontology.get_annotations(fmt),
    )
