"""FastAPI router for the ``/validate`` endpoint.

Validates an uploaded file against a required format using the external
``format_validator`` module with custom request builder and response handler.
"""

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.exceptions import HTTPException

from adapter.request_builder import HTTPValidationRequestBuilder, ValidationRequestDTO
from adapter.response_handler import HTTPValidationResponseHandler
from api.dependencies import get_format_translator, get_validation_request
from api.schemas.validation import FileFormatValidationRequest, FileFormatValidationResponse
from format_validator import FormatTranslator, FormatValidator, ValidationMode

router = APIRouter(tags=["validation"])


def _resolve_mode(mode: str) -> ValidationMode:
    """Convert a mode string to a ``ValidationMode`` enum member.

    Raises ``HTTPException`` when the mode is not recognised.
    """
    try:
        return ValidationMode(mode.lower())
    except ValueError as exc:
        valid_modes = [m.value for m in ValidationMode]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid validation mode '{mode}'. Valid modes: {valid_modes}",
        ) from exc


def _resolve_format(
    ontology_namespace: str, format_identifier: str, translator: FormatTranslator
) -> None:
    """Verify that the format identifier can be mapped for the given ontology.

    Raises ``HTTPException`` when the mapping does not exist.
    """
    if translator.to_local(format_identifier, ontology_namespace) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Format identifier '{format_identifier}' not supported "
                f"for ontology namespace '{ontology_namespace}'"
            ),
        )


@router.post(
    "/validate",
    response_model=FileFormatValidationResponse,
    summary="Validate a file against a required format",
    response_description="Validation outcome with errors, warnings, and infos.",
)
async def validate_file(
    file: UploadFile = File(..., description="The file to validate."),
    request: FileFormatValidationRequest = Depends(get_validation_request),
    translator: FormatTranslator = Depends(get_format_translator),
) -> FileFormatValidationResponse:
    """Validate an uploaded file against the specified format.

    The format identifier is translated via ``FormatTranslator`` into a
    ``FormatIdentifier`` understood by the validator module.
    """
    # --- up-front validation -------------------------------------------------
    validation_mode = _resolve_mode(request.mode)
    _resolve_format(request.ontology_namespace, request.format_identifier, translator)

    # --- persist uploaded file to a temp location ----------------------------
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        # --- build request via the adapter -----------------------------------
        dto = ValidationRequestDTO(
            ontology_namespace=request.ontology_namespace,
            format_identifier=request.format_identifier,
            mode=validation_mode,
            file_path=tmp_path,
            expected_crs=request.expected_crs,
            expected_geometry_type=request.expected_geometry_type,
        )
        builder = HTTPValidationRequestBuilder(dto, translator)
        handler = HTTPValidationResponseHandler()

        # --- run validation --------------------------------------------------
        validator = FormatValidator(builder, handler)
        result = validator.run()

        # The handler always returns a FileFormatValidationResponse model
        return result  # type: ignore[return-value]
    finally:
        # --- cleanup ---------------------------------------------------------
        tmp_path.unlink(missing_ok=True)
