"""Resolve client paths on shared storage to paths the service can read."""

import posixpath
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from config import SharedDir


class PathNotShared(Exception):
    """The path is outside every shared directory, or cannot be accessed."""


class SharedPathResolver:
    """Map client (host) paths into the service's view of the shared directories.

    A path is accepted only if it lies inside a shared directory, both before
    and after following symlinks.
    """

    def __init__(self, shared_dirs: Iterable[SharedDir]):
        # Most specific first, so nested shared dirs map via the deepest match.
        self._dirs = sorted(shared_dirs, key=lambda d: len(d.host.parts), reverse=True)
        self._container_roots = [d.container.resolve() for d in self._dirs]

    @property
    def enabled(self) -> bool:
        """Whether any shared directory is configured."""
        return bool(self._dirs)

    def resolve(self, client_path: str) -> Path:
        """Return the path under which the service reads ``client_path``.

        The checks run in an order that does not reveal whether files outside
        the shared directories exist: the containment check comes before any
        filesystem access.

        The returned path is mapped but not symlink-resolved, so multi-file
        formats keep the directory layout and file names the client sees.

        Raises:
            ValueError: ``client_path`` is not absolute.
            PathNotShared: The path is outside every shared directory, escapes
                one via a symlink, or cannot be accessed.
            FileNotFoundError: The path is inside a shared directory but does
                not exist.
        """
        if not PurePosixPath(client_path).is_absolute():
            raise ValueError(f"Path must be absolute: '{client_path}'")

        # Lexical normalisation collapses '..' before the containment check.
        normalised = PurePosixPath(posixpath.normpath(client_path))
        for shared in self._dirs:
            if normalised.is_relative_to(shared.host):
                mapped = shared.container / normalised.relative_to(shared.host)
                break
        else:
            raise PathNotShared(f"'{client_path}' is not inside a shared directory")

        try:
            resolved = mapped.resolve(strict=True)
        except FileNotFoundError:
            raise FileNotFoundError(f"'{client_path}' does not exist") from None
        except OSError as exc:
            raise PathNotShared(f"'{client_path}' cannot be accessed: {exc.strerror}") from None

        if not any(resolved.is_relative_to(root) for root in self._container_roots):
            raise PathNotShared(f"'{client_path}' links outside the shared directories")
        return mapped
