"""FastAPI router for the ``/compatibility`` endpoint.

Performs ontology-based static compatibility checks between two format
identifiers.
"""

import httpx
from fastapi import APIRouter, HTTPException, status

from api.dependencies import get_ontology_registry
from api.schemas.compatibility import CompatibilityRequest, CompatibilityResponse
from service.compatibility_service import CompatibilityService

router = APIRouter(tags=["compatibility"])


@router.post(
    "/compatibility",
    response_model=CompatibilityResponse,
    summary="Check format compatibility",
    response_description="Compatibility result with explanatory message.",
)
async def check_compatibility(
    request: CompatibilityRequest,
) -> CompatibilityResponse:
    """Check whether the *actual* format satisfies the *expected* format.

    Resolves the ontology schema from the provided URL, then evaluates
    ``rdfs:subClassOf`` and ``owl:equivalentClass`` relationships.
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

    result = CompatibilityService.check(
        expected=request.expected_format,
        actual=request.actual_format,
        ontology=ontology,
    )

    return CompatibilityResponse(
        compatible=result.compatible,
        expected=result.expected,
        actual=result.actual,
        message=result.message,
    )
