"""FastAPI router for the ``/compatibility`` endpoint.

Performs ontology-based static compatibility checks between two format
identifiers.
"""

import httpx
from fastapi import APIRouter, HTTPException, status

from api.dependencies import check_formats_defined, get_ontology_registry
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

    Status codes:

    - ``200``: both formats are defined; ``compatible`` holds the result.
    - ``400``: the ontology schema could not be parsed.
    - ``404``: a local (``file://``) ontology schema does not exist.
    - ``422``: the request body is invalid, or ``expected_format`` and/or
      ``actual_format`` is not defined in the ontology. In the latter case
      ``detail`` is ``{"message": ..., "unknown_formats": [<expanded IRIs>]}``.
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
        [request.expected_format, request.actual_format],
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )

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
