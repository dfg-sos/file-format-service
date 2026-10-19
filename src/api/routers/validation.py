"""FastAPI router for the ``/validate`` endpoints.

Validates a file against a required format using the external
``format_validator`` module with custom request builder and response handler.
The file is either uploaded (``/validate``) or read in place from storage
shared with the client (``/validate/local``).

Both endpoints report the duration of their steps in a ``Server-Timing``
response header.
"""

import shutil
import tempfile
import time
from pathlib import Path, PureWindowsPath

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from fastapi.exceptions import HTTPException
from format_validator import FormatTranslator, FormatValidator, ValidationMode

from adapter.request_builder import HTTPValidationRequestBuilder, ValidationRequestDTO
from adapter.response_handler import HTTPValidationResponseHandler
from api.dependencies import get_format_translator, get_shared_path_resolver, get_validation_request
from api.schemas.validation import (
    FileFormatValidationRequest,
    FileFormatValidationResponse,
    LocalValidationRequest,
)
from service.shared_paths import PathNotShared, SharedPathResolver

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


def _resolve_shared_path(client_path: str, resolver: SharedPathResolver) -> Path:
    """Map a client path into the service's view of the shared directories.

    Raises ``HTTPException`` (400 relative path, 403 outside the shared
    directories, 404 missing file).
    """
    try:
        return resolver.resolve(client_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PathNotShared as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def _server_timing(**durations_ms: float) -> str:
    """Format a ``Server-Timing`` header value, e.g. ``validate;dur=12.3``."""
    return ", ".join(f"{name};dur={ms:.1f}" for name, ms in durations_ms.items())


def _run_validation(
    request: FileFormatValidationRequest,
    mode: ValidationMode,
    file_path: Path,
    secondary_file_paths: set[Path],
    translator: FormatTranslator,
) -> FileFormatValidationResponse:
    """Validate the given files via the adapter and ``FormatValidator``."""
    dto = ValidationRequestDTO(
        ontology_namespace=request.ontology_namespace,
        format_identifier=request.format_identifier,
        mode=mode,
        file_path=file_path,
        secondary_file_paths=secondary_file_paths,
        expected_crs=request.expected_crs,
        expected_geometry_type=request.expected_geometry_type,
    )
    builder = HTTPValidationRequestBuilder(dto, translator)
    handler = HTTPValidationResponseHandler()
    # The handler always returns a FileFormatValidationResponse model
    return FormatValidator(builder, handler).run()  # type: ignore[return-value]


@router.post(
    "/validate",
    response_model=FileFormatValidationResponse,
    summary="Validate a file against a required format",
    response_description="Validation outcome with errors, warnings, and infos.",
)
async def validate_file(
    response: Response,
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
        start = time.perf_counter()
        taken: set[str] = set()
        primary_path = _save_upload(file, tmp_dir, "upload", taken)
        secondary_paths = {
            _save_upload(upload, tmp_dir, f"secondary_{i}", taken) for i, upload in enumerate(secondary_files)
        }
        receive_ms = _elapsed_ms(start)

        # --- run validation --------------------------------------------------
        start = time.perf_counter()
        result = _run_validation(request, validation_mode, primary_path, secondary_paths, translator)
        response.headers["Server-Timing"] = _server_timing(receive=receive_ms, validate=_elapsed_ms(start))
        return result
    finally:
        # --- cleanup ---------------------------------------------------------
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post(
    "/validate/local",
    response_model=FileFormatValidationResponse,
    summary="Validate a file on shared storage without uploading it",
    response_description="Validation outcome with errors, warnings, and infos.",
)
async def validate_local_file(
    request: LocalValidationRequest,
    response: Response,
    translator: FormatTranslator = Depends(get_format_translator),
    resolver: SharedPathResolver = Depends(get_shared_path_resolver),
) -> FileFormatValidationResponse:
    """Validate a file that the service can read in place.

    Gives the same result as uploading the file to ``/validate``, but the file
    is neither transferred nor copied. Paths are given as the client sees them
    and are mapped via ``SOS_FFS_SHARED_DIRS``; the service only reads them.

    Status codes:

    - ``200``: validation ran; ``status`` holds the outcome.
    - ``400``: a path is not absolute, the mode is invalid, or the format
      is not supported.
    - ``403``: local validation is disabled (no shared directories
      configured), or a path is outside the shared directories, including via
      ``..`` or symlinks. Clients can fall back to ``/validate``.
    - ``404``: a path inside a shared directory does not exist.
    - ``422``: the request body is invalid.
    """
    if not resolver.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local validation is disabled: no shared directories configured",
        )

    # --- up-front validation -------------------------------------------------
    validation_mode = _resolve_mode(request.mode)
    _resolve_format(request.ontology_namespace, request.format_identifier, translator)

    # --- map client paths onto shared storage --------------------------------
    start = time.perf_counter()
    primary_path = _resolve_shared_path(request.file_path, resolver)
    secondary_paths = {_resolve_shared_path(path, resolver) for path in request.secondary_file_paths}
    resolve_ms = _elapsed_ms(start)

    # --- run validation ------------------------------------------------------
    start = time.perf_counter()
    result = _run_validation(request, validation_mode, primary_path, secondary_paths, translator)
    response.headers["Server-Timing"] = _server_timing(resolve=resolve_ms, validate=_elapsed_ms(start))
    return result
