"""FastAPI router for the ``/validate/{mode}`` endpoints.

Validates a file against a required format using the external
``format_validator`` module: the request is built first, so requests that
cannot be validated are rejected before any file is written or read.
There is one endpoint per validation mode:

- ``/validate/basic`` checks only file names, so the client sends paths and
  the service never touches the files.
- ``/validate/structural`` and ``/validate/full`` take uploaded files; their
  ``/local`` variants read the files in place from storage shared with the
  client.

The endpoints report the duration of their steps in a ``Server-Timing``
response header. They are synchronous so that FastAPI runs them in its thread
pool: validation blocks on file I/O and must not stall the event loop.
"""

import shutil
import tempfile
import time
from dataclasses import replace
from pathlib import Path, PureWindowsPath

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from fastapi.exceptions import HTTPException
from format_validator import (
    FileInput,
    FormatTranslator,
    InvalidRequest,
    MultiFileInput,
    ValidationMode,
    ValidationRequest,
    ValidationResult,
    build_request,
    validate,
)

from api.dependencies import (
    get_format_translator,
    get_full_upload_request,
    get_shared_path_resolver,
    get_upload_request,
)
from api.schemas.validation import (
    FileFormatValidationEvent,
    FileFormatValidationRequest,
    FileFormatValidationResponse,
    FullPathValidationRequest,
    FullValidationRequest,
    PathValidationRequest,
)
from service.shared_paths import PathNotShared, SharedPathResolver

router = APIRouter(tags=["validation"])

_PRIMARY_FILE = File(
    ...,
    description="The file to validate. For multi-file formats (e.g. Shapefile) this is the primary file (e.g. the .shp).",
)
_SECONDARY_FILES = File(
    default=[],
    description=(
        "Additional files belonging to a multi-file format (e.g. .shx, .dbf, .prj for a Shapefile). "
        "Repeat the field once per file. File names must be preserved."
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


def _plan_uploads(file: UploadFile, secondary_files: list[UploadFile], directory: Path) -> list[tuple[UploadFile, Path]]:
    """Assign each upload its target path in ``directory``, primary file first.

    Nothing is written yet, so a request that cannot be validated costs no
    disk I/O. Raises ``HTTPException`` (400) for duplicate file names.
    """
    uploads = [(file, "upload"), *((upload, f"secondary_{i}") for i, upload in enumerate(secondary_files))]
    planned: dict[str, tuple[UploadFile, Path]] = {}
    for upload, fallback in uploads:
        name = _safe_filename(upload, fallback)
        if name.lower() in planned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate file name '{name}' in upload",
            )
        planned[name.lower()] = (upload, directory / name)
    return list(planned.values())


def _write_upload(upload: UploadFile, target: Path) -> None:
    with target.open("wb") as out:
        shutil.copyfileobj(upload.file, out)


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


def _file_input(primary: Path, secondary: set[Path]) -> FileInput:
    return MultiFileInput(primary, secondary) if secondary else FileInput(primary)


def _build_request(
    request: FileFormatValidationRequest,
    mode: ValidationMode,
    file_input: FileInput,
    translator: FormatTranslator,
) -> ValidationRequest:
    """Build the validator's request; the files are not read.

    Raises ``HTTPException`` (400) when the format is not mapped or has no
    validator, or ``expected_metadata`` has keys or values the format's
    validator does not support.
    """
    format_id = translator.to_local(request.ontology_namespace + request.format_identifier)
    if format_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Format identifier '{request.format_identifier}' not supported "
                f"for ontology namespace '{request.ontology_namespace}'"
            ),
        )
    expected_metadata = request.expected_metadata if isinstance(request, FullValidationRequest) else None
    try:
        return build_request(format_id, file_input, mode, expected_metadata)
    except InvalidRequest as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _to_response(validation_result: ValidationResult) -> FileFormatValidationResponse:
    """Convert a ``ValidationResult`` into a ``FileFormatValidationResponse``."""
    data = validation_result.to_dict()

    return FileFormatValidationResponse(
        status=data["status"].upper(),
        errors=[FileFormatValidationEvent(**e) for e in data["errors"]],
        warnings=[FileFormatValidationEvent(**e) for e in data["warnings"]],
        infos=[FileFormatValidationEvent(**e) for e in data["infos"]],
    )


def _validate_upload(
    mode: ValidationMode,
    request: FileFormatValidationRequest,
    file: UploadFile,
    secondary_files: list[UploadFile],
    response: Response,
    translator: FormatTranslator,
) -> FileFormatValidationResponse:
    """Validate uploaded files, stored in a private temp directory meanwhile.

    The request is built before the uploads are written, so a request that
    cannot be validated is rejected without writing anything.
    """
    # The directory keeps the original file names so that multi-file formats
    # (which match components by stem) stay intact.
    tmp_dir = Path(tempfile.mkdtemp(prefix="sos_validate_"))
    try:
        # --- build the request from the planned paths ------------------------
        planned = _plan_uploads(file, secondary_files, tmp_dir)
        file_input = _file_input(planned[0][1], {target for _, target in planned[1:]})
        validation_request = _build_request(request, mode, file_input, translator)

        # --- persist uploaded files ------------------------------------------
        start = time.perf_counter()
        for upload, target in planned:
            _write_upload(upload, target)
        receive_ms = _elapsed_ms(start)

        # --- run validation --------------------------------------------------
        start = time.perf_counter()
        result = _to_response(validate(validation_request))
        response.headers["Server-Timing"] = _server_timing(receive=receive_ms, validate=_elapsed_ms(start))
        return result
    finally:
        # --- cleanup ---------------------------------------------------------
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _validate_local(
    mode: ValidationMode,
    request: PathValidationRequest,
    response: Response,
    translator: FormatTranslator,
    resolver: SharedPathResolver,
) -> FileFormatValidationResponse:
    """Validate files the service reads in place from shared storage."""
    if not resolver.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local validation is disabled: no shared directories configured",
        )

    # --- build the request from the client paths -----------------------------
    client_input = _file_input(Path(request.file_path), {Path(path) for path in request.secondary_file_paths})
    validation_request = _build_request(request, mode, client_input, translator)

    # --- map client paths onto shared storage --------------------------------
    start = time.perf_counter()
    primary_path = _resolve_shared_path(request.file_path, resolver)
    secondary_paths = {_resolve_shared_path(path, resolver) for path in request.secondary_file_paths}
    validation_request = replace(validation_request, actual_file=_file_input(primary_path, secondary_paths))
    resolve_ms = _elapsed_ms(start)

    # --- run validation ------------------------------------------------------
    start = time.perf_counter()
    result = _to_response(validate(validation_request))
    response.headers["Server-Timing"] = _server_timing(resolve=resolve_ms, validate=_elapsed_ms(start))
    return result


@router.post(
    "/validate/basic",
    response_model=FileFormatValidationResponse,
    summary="Validate a file name against a required format",
    response_description="Validation outcome with errors, warnings, and infos.",
)
def validate_basic(
    request: PathValidationRequest,
    response: Response,
    translator: FormatTranslator = Depends(get_format_translator),
) -> FileFormatValidationResponse:
    """Check the file names (extensions and, for multi-file formats, the
    components present) against the specified format.

    Only the paths are inspected: the files are neither transferred nor read,
    and need not be accessible to the service.
    """
    file_input = _file_input(Path(request.file_path), {Path(path) for path in request.secondary_file_paths})
    validation_request = _build_request(request, ValidationMode.BASIC, file_input, translator)

    start = time.perf_counter()
    result = _to_response(validate(validation_request))
    response.headers["Server-Timing"] = _server_timing(validate=_elapsed_ms(start))
    return result


@router.post(
    "/validate/structural",
    response_model=FileFormatValidationResponse,
    summary="Validate the structure of uploaded files",
    response_description="Validation outcome with errors, warnings, and infos.",
)
def validate_structural(
    response: Response,
    file: UploadFile = _PRIMARY_FILE,
    secondary_files: list[UploadFile] = _SECONDARY_FILES,
    request: FileFormatValidationRequest = Depends(get_upload_request),
    translator: FormatTranslator = Depends(get_format_translator),
) -> FileFormatValidationResponse:
    """Validate uploaded files structurally against the specified format.

    Multi-file formats are supported by uploading the primary file as ``file``
    and the remaining components as repeated ``secondary_files`` parts.
    """
    return _validate_upload(ValidationMode.STRUCTURAL, request, file, secondary_files, response, translator)


@router.post(
    "/validate/structural/local",
    response_model=FileFormatValidationResponse,
    summary="Validate the structure of files on shared storage without uploading them",
    response_description="Validation outcome with errors, warnings, and infos.",
)
def validate_structural_local(
    request: PathValidationRequest,
    response: Response,
    translator: FormatTranslator = Depends(get_format_translator),
    resolver: SharedPathResolver = Depends(get_shared_path_resolver),
) -> FileFormatValidationResponse:
    """Like ``/validate/structural``, but the files are read in place.

    Paths are given as the client sees them and are mapped via
    ``SOS_FFS_SHARED_DIRS``; the service only reads them.

    Status codes:

    - ``200``: validation ran; ``status`` holds the outcome.
    - ``400``: a path is not absolute, or the format is not supported.
    - ``403``: local validation is disabled (no shared directories
      configured), or a path is outside the shared directories, including via
      ``..`` or symlinks. Clients can fall back to the upload endpoint.
    - ``404``: a path inside a shared directory does not exist.
    - ``422``: the request body is invalid.
    """
    return _validate_local(ValidationMode.STRUCTURAL, request, response, translator, resolver)


@router.post(
    "/validate/full",
    response_model=FileFormatValidationResponse,
    summary="Fully validate uploaded files, including their metadata",
    response_description="Validation outcome with errors, warnings, and infos.",
)
def validate_full(
    response: Response,
    file: UploadFile = _PRIMARY_FILE,
    secondary_files: list[UploadFile] = _SECONDARY_FILES,
    request: FullValidationRequest = Depends(get_full_upload_request),
    translator: FormatTranslator = Depends(get_format_translator),
) -> FileFormatValidationResponse:
    """Open uploaded files and validate them against the specified format.

    ``expected_metadata`` is a JSON object whose supported keys depend on the
    validator of the format.
    """
    return _validate_upload(ValidationMode.FULL, request, file, secondary_files, response, translator)


@router.post(
    "/validate/full/local",
    response_model=FileFormatValidationResponse,
    summary="Fully validate files on shared storage without uploading them",
    response_description="Validation outcome with errors, warnings, and infos.",
)
def validate_full_local(
    request: FullPathValidationRequest,
    response: Response,
    translator: FormatTranslator = Depends(get_format_translator),
    resolver: SharedPathResolver = Depends(get_shared_path_resolver),
) -> FileFormatValidationResponse:
    """Like ``/validate/full``, but the files are read in place.

    Paths are given as the client sees them and are mapped via
    ``SOS_FFS_SHARED_DIRS``; the service only reads them.

    Status codes:

    - ``200``: validation ran; ``status`` holds the outcome.
    - ``400``: a path is not absolute, the format is not supported, or
      ``expected_metadata`` has keys or values the format's validator does
      not support.
    - ``403``: local validation is disabled (no shared directories
      configured), or a path is outside the shared directories, including via
      ``..`` or symlinks. Clients can fall back to the upload endpoint.
    - ``404``: a path inside a shared directory does not exist.
    - ``422``: the request body is invalid.
    """
    return _validate_local(ValidationMode.FULL, request, response, translator, resolver)
