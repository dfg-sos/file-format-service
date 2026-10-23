"""Stage uploaded files in a private temp directory for validation."""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

from fastapi import UploadFile
from format_validator import FileInput, InvalidRequest

from service.validation import file_input


class DuplicateFileName(InvalidRequest):
    """Two uploads of one request have the same file name."""


def safe_filename(upload: UploadFile, fallback: str) -> str:
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


class StagedUploads:
    """Uploads with their target paths in a directory, written only on ``write()``.

    The targets keep the original file names so that multi-file formats (which
    match components by stem) stay intact.
    """

    def __init__(self, file: UploadFile, secondary_files: list[UploadFile], directory: Path):
        """Plan the target paths, primary file first; nothing is written yet.

        Raises:
            DuplicateFileName: Two uploads have the same name, ignoring case.
        """
        uploads = [(file, "upload"), *((upload, f"secondary_{i}") for i, upload in enumerate(secondary_files))]
        planned: dict[str, tuple[UploadFile, Path]] = {}
        for upload, fallback in uploads:
            name = safe_filename(upload, fallback)
            if name.lower() in planned:
                raise DuplicateFileName(f"Duplicate file name '{name}' in upload")
            planned[name.lower()] = (upload, directory / name)
        self._planned = list(planned.values())

    @property
    def file_input(self) -> FileInput:
        """The target paths as the validator's input."""
        return file_input(self._planned[0][1], {target for _, target in self._planned[1:]})

    def write(self) -> None:
        """Write every upload to its target path."""
        for upload, target in self._planned:
            with target.open("wb") as out:
                shutil.copyfileobj(upload.file, out)


@contextmanager
def staged_uploads(file: UploadFile, secondary_files: list[UploadFile]) -> Iterator[StagedUploads]:
    """Stage uploads in a new temp directory that is deleted on exit.

    Raises:
        DuplicateFileName: Two uploads have the same name, ignoring case.
    """
    directory = Path(tempfile.mkdtemp(prefix="sos_validate_"))
    try:
        yield StagedUploads(file, secondary_files, directory)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
