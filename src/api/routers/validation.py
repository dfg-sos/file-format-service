"""FastAPI router for the ``/validate`` endpoint.

Validates an uploaded file against a required format using the external
``format_validator`` module with custom request builder and response handler.
"""

import shutil
import tempfile
from pathlib import Path, PureWindowsPath

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


def _safe_filename(upload: UploadFile, fallback: str) -> str:
    """Return the bare, client-supplied file name of an upload.

    Directory components are stripped to prevent path traversal. The original
    name is kept (rather than a random one) because multi-file formats such as
    Shapefiles rely on the components sharing a stem.
    """
    raw = upload.filename or fallback
    # PureWindowsPath splits on both '/' and '\\', so this handles Unix and Windows paths.
    name = PureWindowsPath(raw).name
    if name in ("", ".", ".."):
        return fallback
    return name


def _save_upload(upload: UploadFile, directory: Path, fallback: str, taken: set[str]) -> Path:
    """Persist an upload into ``directory`` under its own file name."""
    name = _safe_filename(upload, fallback)
    if name.lower() in taken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Duplicate file name '{name}' in upload",
        )
    taken.add(name.lower())
    target = directory / name
    with target.open("wb") as out:
        shutil.copyfileobj(upload.file, out)
    return target


@router.post(
    "/validate",
    response_model=FileFormatValidationResponse,
    summary="Validate a file against a required format",
    response_description="Validation outcome with errors, warnings, and infos.",
)
async def validate_file(
    file: UploadFile = File(
        ...,
        description="The file to validate. For multi-file formats (e.g. Shapefile) this is the primary file (e.g. the .shp).",
    ),
    secondary_files: list[UploadFile] = File(
        default=[],
        description=(
            "Additional files belonging to a multi-file format (e.g. .shx, .dbf, .prj for a Shapefile). "
            "Repeat the field once per file. File names must be preserved."
        ),
    ),
    request: FileFormatValidationRequest = Depends(get_validation_request),
    translator: FormatTranslator = Depends(get_format_translator),
) -> FileFormatValidationResponse:
    """Validate an uploaded file against the specified format.

    The format identifier is translated via ``FormatTranslator`` into a
    ``FormatIdentifier`` understood by the validator module. Multi-file formats
    are supported by uploading the primary file as ``file`` and the remaining
    components as repeated ``secondary_files`` parts.
    """
    # --- up-front validation -------------------------------------------------
    validation_mode = _resolve_mode(request.mode)
    # fails when format is not supported
    _resolve_format(request.ontology_namespace, request.format_identifier, translator) 

    # --- persist uploaded files into a private temp directory ----------------
    # The directory keeps the original file names so that multi-file formats
    # (which match components by stem) stay intact.
    tmp_dir = Path(tempfile.mkdtemp(prefix="sos_validate_"))
    try:
        taken: set[str] = set()
        primary_path = _save_upload(file, tmp_dir, "upload", taken)
        secondary_paths = {
            _save_upload(upload, tmp_dir, f"secondary_{i}", taken) for i, upload in enumerate(secondary_files)
        }

        # --- build request via the adapter -----------------------------------
        dto = ValidationRequestDTO(
            ontology_namespace=request.ontology_namespace,
            format_identifier=request.format_identifier,
            mode=validation_mode,
            file_path=primary_path,
            secondary_file_paths=secondary_paths,
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
        shutil.rmtree(tmp_dir, ignore_errors=True)
