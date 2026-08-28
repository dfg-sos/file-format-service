"""FastAPI router for the ``/compatibility`` endpoint.

Performs ontology-based static compatibility checks between two format
identifiers.
"""

from fastapi import APIRouter, Depends

from api.dependencies import get_compatibility_service
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
    service: CompatibilityService = Depends(get_compatibility_service),
) -> CompatibilityResponse:
    """Check whether the *actual* format satisfies the *expected* format.

    Uses the loaded OWL ontology to evaluate ``rdfs:subClassOf`` and
    ``owl:equivalentClass`` relationships.
    """
    result = service.check(
        expected=request.expected_format,
        actual=request.actual_format,
        ontology_source=request.ontology_uri,
    )

    return CompatibilityResponse(
        compatible=result.compatible,
        expected=result.expected,
        actual=result.actual,
        message=result.message,
        ontology_source=result.ontology_source,
    )
