"""FastAPI router for the ``/validate/{mode}`` endpoints.

Validates a file against a required format using the external
``format_validator`` module: the request is built first, so requests that
cannot be validated are rejected before any file is written or read.
There is one endpoint per validation mode:

- ``/validate/basic`` checks only file names, so the client sends paths and
  the service never touches the files.
- ``/validate/metadata`` and ``/validate/content`` take uploaded files; their
  ``/local`` variants read the files in place from storage shared with the
  client. ``metadata`` reads only the header or declarations of a file,
  ``content`` also reads every pixel, feature or record.

The endpoints report the duration of their steps in a ``Server-Timing``
response header. Request errors raised by the service layer are mapped to
status codes by the exception handlers in ``api.app``. They are synchronous so that FastAPI runs them in its thread
pool: validation blocks on file I/O and must not stall the event loop.
"""

from dataclasses import replace
from pathlib import Path

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from fastapi.exceptions import HTTPException
from format_validator import FormatTranslator, ValidationMode, validate

from api.dependencies import (
    get_format_translator,
    get_metadata_upload_request,
    get_shared_path_resolver,
    get_upload_request,
)
from api.schemas.validation import (
    FileFormatValidationRequest,
    FileFormatValidationResponse,
    MetadataPathValidationRequest,
    MetadataValidationRequest,
    PathValidationRequest,
)
from api.timing import ServerTiming
from service.shared_paths import SharedPathResolver
from service.uploads import staged_uploads
from service.validation import build_validation_request, file_input

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


def _expected_metadata(request: FileFormatValidationRequest) -> dict[str, str] | None:
    return request.expected_metadata if isinstance(request, MetadataValidationRequest) else None


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
    timing = ServerTiming()
    with staged_uploads(file, secondary_files) as staged:
        validation_request = build_validation_request(
            request.ontology_namespace,
            request.format_identifier,
            mode,
            staged.file_input,
            translator,
            _expected_metadata(request),
        )
        with timing("receive"):
            staged.write()
        with timing("validate"):
            result = validate(validation_request)
    response.headers["Server-Timing"] = str(timing)
    return FileFormatValidationResponse.from_result(result)


def _validate_local(
    mode: ValidationMode,
    request: PathValidationRequest,
    response: Response,
    translator: FormatTranslator,
    resolver: SharedPathResolver,
) -> FileFormatValidationResponse:
    """Validate files the service reads in place from shared storage.

    The request is built from the client paths first, so a request that cannot
    be validated is rejected before any path is looked at.
    """
    if not resolver.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local validation is disabled: no shared directories configured",
        )

    timing = ServerTiming()
    client_input = file_input(Path(request.file_path), {Path(path) for path in request.secondary_file_paths})
    validation_request = build_validation_request(
        request.ontology_namespace,
        request.format_identifier,
        mode,
        client_input,
        translator,
        _expected_metadata(request),
    )
    with timing("resolve"):
        mapped_input = file_input(
            resolver.resolve(request.file_path),
            {resolver.resolve(path) for path in request.secondary_file_paths},
        )
    with timing("validate"):
        result = validate(replace(validation_request, actual_file=mapped_input))
    response.headers["Server-Timing"] = str(timing)
    return FileFormatValidationResponse.from_result(result)


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
    timing = ServerTiming()
    validation_request = build_validation_request(
        request.ontology_namespace,
        request.format_identifier,
        ValidationMode.BASIC,
        file_input(Path(request.file_path), {Path(path) for path in request.secondary_file_paths}),
        translator,
    )
    with timing("validate"):
        result = validate(validation_request)
    response.headers["Server-Timing"] = str(timing)
    return FileFormatValidationResponse.from_result(result)


@router.post(
    "/validate/metadata",
    response_model=FileFormatValidationResponse,
    summary="Validate the header and metadata of uploaded files",
    response_description="Validation outcome with errors, warnings, and infos.",
)
def validate_metadata(
    response: Response,
    file: UploadFile = _PRIMARY_FILE,
    secondary_files: list[UploadFile] = _SECONDARY_FILES,
    request: MetadataValidationRequest = Depends(get_metadata_upload_request),
    translator: FormatTranslator = Depends(get_format_translator),
) -> FileFormatValidationResponse:
    """Open uploaded files as the format and check their header or declarations, including their metadata.

    Only the header is read, so the cost does not grow with the file size.

    Multi-file formats are supported by uploading the primary file as ``file``
    and the remaining components as repeated ``secondary_files`` parts.
    ``expected_metadata`` is a JSON object whose supported keys depend on the
    validator of the format.
    """
    return _validate_upload(ValidationMode.METADATA, request, file, secondary_files, response, translator)


@router.post(
    "/validate/metadata/local",
    response_model=FileFormatValidationResponse,
    summary="Validate the header and metadata of files on shared storage without uploading them",
    response_description="Validation outcome with errors, warnings, and infos.",
)
def validate_metadata_local(
    request: MetadataPathValidationRequest,
    response: Response,
    translator: FormatTranslator = Depends(get_format_translator),
    resolver: SharedPathResolver = Depends(get_shared_path_resolver),
) -> FileFormatValidationResponse:
    """Like ``/validate/metadata``, but the files are read in place.

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
    return _validate_local(ValidationMode.METADATA, request, response, translator, resolver)


@router.post(
    "/validate/content",
    response_model=FileFormatValidationResponse,
    summary="Validate the header, metadata and content of uploaded files",
    response_description="Validation outcome with errors, warnings, and infos.",
)
def validate_content(
    response: Response,
    file: UploadFile = _PRIMARY_FILE,
    secondary_files: list[UploadFile] = _SECONDARY_FILES,
    request: MetadataValidationRequest = Depends(get_metadata_upload_request),
    translator: FormatTranslator = Depends(get_format_translator),
) -> FileFormatValidationResponse:
    """Like ``/validate/metadata``, then read every pixel, feature or record of the files.

    The content is read only if the metadata checks did not fail.

    Multi-file formats are supported by uploading the primary file as ``file``
    and the remaining components as repeated ``secondary_files`` parts.
    ``expected_metadata`` is a JSON object whose supported keys depend on the
    validator of the format.
    """
    return _validate_upload(ValidationMode.CONTENT, request, file, secondary_files, response, translator)


@router.post(
    "/validate/content/local",
    response_model=FileFormatValidationResponse,
    summary="Validate the header, metadata and content of files on shared storage without uploading them",
    response_description="Validation outcome with errors, warnings, and infos.",
)
def validate_content_local(
    request: MetadataPathValidationRequest,
    response: Response,
    translator: FormatTranslator = Depends(get_format_translator),
    resolver: SharedPathResolver = Depends(get_shared_path_resolver),
) -> FileFormatValidationResponse:
    """Like ``/validate/content``, but the files are read in place.

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
    return _validate_local(ValidationMode.CONTENT, request, response, translator, resolver)
