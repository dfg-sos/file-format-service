"""Unit tests for ``SOS_FFS_SHARED_DIRS`` parsing and the ``SharedPathResolver``."""

import os
from pathlib import Path, PurePosixPath

import pytest
from pydantic import ValidationError

from config import Settings, SharedDir
from service.shared_paths import PathNotShared, SharedPathResolver


class TestParseSharedDirs:
    def _parse(self, monkeypatch: pytest.MonkeyPatch, value: str) -> list[SharedDir]:
        monkeypatch.setenv("SOS_FFS_SHARED_DIRS", value)
        return Settings().shared_dirs

    def test_unset_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SOS_FFS_SHARED_DIRS", raising=False)
        assert Settings().shared_dirs == []

    def test_empty_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._parse(monkeypatch, "") == []

    def test_host_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._parse(monkeypatch, "/data") == [SharedDir(PurePosixPath("/data"), Path("/data"))]

    def test_host_and_container(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._parse(monkeypatch, "/home/user/data:/data") == [
            SharedDir(PurePosixPath("/home/user/data"), Path("/data"))
        ]

    def test_multiple_with_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._parse(monkeypatch, " /home/user/data : /data , /scratch ,") == [
            SharedDir(PurePosixPath("/home/user/data"), Path("/data")),
            SharedDir(PurePosixPath("/scratch"), Path("/scratch")),
        ]

    @pytest.mark.parametrize("value", ["data", "/data:data", "data:/data"])
    def test_relative_path_rejected(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        with pytest.raises(ValidationError):
            self._parse(monkeypatch, value)


@pytest.fixture
def shared(tmp_path: Path) -> Path:
    """A shared directory with one file; ``tmp_path`` itself is not shared."""
    root = tmp_path / "shared"
    root.mkdir()
    (root / "data.geojson").write_text("{}")
    return root


@pytest.fixture
def resolver(shared: Path) -> SharedPathResolver:
    return SharedPathResolver([SharedDir(PurePosixPath(shared), shared)])


class TestEnabled:
    def test_disabled_without_shared_dirs(self) -> None:
        assert SharedPathResolver([]).enabled is False

    def test_enabled_with_shared_dirs(self, resolver: SharedPathResolver) -> None:
        assert resolver.enabled is True


class TestResolve:
    def test_file_inside_shared_dir(self, resolver: SharedPathResolver, shared: Path) -> None:
        assert resolver.resolve(str(shared / "data.geojson")) == shared / "data.geojson"

    def test_host_path_is_mapped_to_container(self, shared: Path) -> None:
        resolver = SharedPathResolver([SharedDir(PurePosixPath("/home/user/data"), shared)])
        assert resolver.resolve("/home/user/data/data.geojson") == shared / "data.geojson"

    def test_most_specific_shared_dir_wins(self, tmp_path: Path, shared: Path) -> None:
        resolver = SharedPathResolver(
            [
                SharedDir(PurePosixPath("/host"), tmp_path),
                SharedDir(PurePosixPath("/host/nested"), shared),
            ]
        )
        assert resolver.resolve("/host/nested/data.geojson") == shared / "data.geojson"

    def test_dot_segments_are_normalised(self, resolver: SharedPathResolver, shared: Path) -> None:
        assert resolver.resolve(f"{shared}/./sub/../data.geojson") == shared / "data.geojson"

    def test_relative_path_rejected(self, resolver: SharedPathResolver) -> None:
        with pytest.raises(ValueError):
            resolver.resolve("data.geojson")

    def test_outside_shared_dirs_rejected(self, resolver: SharedPathResolver, tmp_path: Path) -> None:
        outside = tmp_path / "outside.geojson"
        outside.write_text("{}")
        with pytest.raises(PathNotShared):
            resolver.resolve(str(outside))

    def test_dotdot_traversal_rejected(self, resolver: SharedPathResolver, shared: Path, tmp_path: Path) -> None:
        (tmp_path / "secret.txt").write_text("x")
        with pytest.raises(PathNotShared):
            resolver.resolve(f"{shared}/../secret.txt")

    def test_sibling_with_common_prefix_rejected(self, resolver: SharedPathResolver, shared: Path) -> None:
        sibling = shared.parent / (shared.name + "2")
        sibling.mkdir()
        (sibling / "data.geojson").write_text("{}")
        with pytest.raises(PathNotShared):
            resolver.resolve(str(sibling / "data.geojson"))

    def test_symlink_escaping_shared_dir_rejected(
        self, resolver: SharedPathResolver, shared: Path, tmp_path: Path
    ) -> None:
        secret = tmp_path / "secret.txt"
        secret.write_text("x")
        (shared / "link.txt").symlink_to(secret)
        with pytest.raises(PathNotShared):
            resolver.resolve(str(shared / "link.txt"))

    def test_symlinked_directory_escaping_shared_dir_rejected(
        self, resolver: SharedPathResolver, shared: Path, tmp_path: Path
    ) -> None:
        (tmp_path / "secret.txt").write_text("x")
        (shared / "escape").symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(PathNotShared):
            resolver.resolve(str(shared / "escape" / "secret.txt"))

    def test_symlink_inside_shared_dir_keeps_link_path(
        self, resolver: SharedPathResolver, shared: Path
    ) -> None:
        staged = shared / "staged"
        staged.mkdir()
        (staged / "input.geojson").symlink_to(shared / "data.geojson")
        assert resolver.resolve(str(staged / "input.geojson")) == staged / "input.geojson"

    def test_missing_file_inside_shared_dir(self, resolver: SharedPathResolver, shared: Path) -> None:
        with pytest.raises(FileNotFoundError):
            resolver.resolve(str(shared / "missing.geojson"))

    def test_missing_file_outside_shared_dirs_is_not_reported_as_missing(
        self, resolver: SharedPathResolver, tmp_path: Path
    ) -> None:
        with pytest.raises(PathNotShared):
            resolver.resolve(str(tmp_path / "missing.geojson"))

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
    def test_inaccessible_path_rejected(self, resolver: SharedPathResolver, shared: Path) -> None:
        locked = shared / "locked"
        locked.mkdir()
        (locked / "data.geojson").write_text("{}")
        locked.chmod(0)
        try:
            with pytest.raises(PathNotShared):
                resolver.resolve(str(locked / "data.geojson"))
        finally:
            locked.chmod(0o755)

    def test_shared_dir_behind_symlink(self, tmp_path: Path, shared: Path) -> None:
        """A container root that is itself a symlink still accepts its own files."""
        link = tmp_path / "mount"
        link.symlink_to(shared, target_is_directory=True)
        resolver = SharedPathResolver([SharedDir(PurePosixPath("/host"), link)])
        assert resolver.resolve("/host/data.geojson") == link / "data.geojson"
