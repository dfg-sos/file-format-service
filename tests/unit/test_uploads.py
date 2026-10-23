"""Unit tests for staging uploads in ``service.uploads``."""

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from format_validator import FileInput, MultiFileInput

from service.uploads import DuplicateFileName, StagedUploads, safe_filename, staged_uploads


def _upload(name: str | None, content: bytes = b"") -> UploadFile:
    return UploadFile(BytesIO(content), filename=name)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("roads.shp", "roads.shp"),
        ("../../etc/passwd", "passwd"),
        ("/abs/path/roads.shp", "roads.shp"),
        ("..\\..\\evil.dll", "evil.dll"),
        ("C:\\Users\\me\\roads.shp", "roads.shp"),
        ("a/b\\c.dbf", "c.dbf"),
        ("dir/", "dir"),
        ("..", "fallback"),
        (".", "fallback"),
        ("", "fallback"),
        (None, "fallback"),
    ],
)
def test_safe_filename(raw: str | None, expected: str) -> None:
    assert safe_filename(_upload(raw), "fallback") == expected


class TestStagedUploads:
    def test_single_file(self, tmp_path: Path) -> None:
        staged = StagedUploads(_upload("a.geojson"), [], tmp_path)
        assert staged.file_input == FileInput(tmp_path / "a.geojson")

    def test_multi_file(self, tmp_path: Path) -> None:
        staged = StagedUploads(_upload("roads.shp"), [_upload("roads.shx"), _upload("roads.dbf")], tmp_path)
        assert isinstance(staged.file_input, MultiFileInput)
        assert staged.file_input.path == tmp_path / "roads.shp"
        assert staged.file_input.files() == {tmp_path / n for n in ("roads.shp", "roads.shx", "roads.dbf")}

    def test_nothing_written_before_write(self, tmp_path: Path) -> None:
        staged = StagedUploads(_upload("a.geojson", b"{}"), [], tmp_path)
        assert list(tmp_path.iterdir()) == []
        staged.write()
        assert (tmp_path / "a.geojson").read_bytes() == b"{}"

    def test_duplicate_names_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(DuplicateFileName, match="ROADS.shp"):
            StagedUploads(_upload("roads.shp"), [_upload("ROADS.shp")], tmp_path)


def test_staged_directory_removed_on_exit() -> None:
    with staged_uploads(_upload("a.geojson", b"{}"), []) as staged:
        staged.write()
        directory = staged.file_input.path.parent
        assert directory.is_dir()
    assert not directory.exists()
