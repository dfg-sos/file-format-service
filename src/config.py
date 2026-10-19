"""Application configuration via pydantic-settings."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


@dataclass(frozen=True)
class SharedDir:
    """A directory shared between clients and the service.

    Attributes:
        host: The directory as clients see it (absolute).
        container: Where the service sees the same directory, e.g. the mount
            point inside a container. Equal to ``host`` without a mapping.
    """

    host: PurePosixPath
    container: Path

    @classmethod
    def parse(cls, entry: str) -> SharedDir:
        """Parse ``host_path`` or ``host_path:container_path``."""
        host, _, container = entry.partition(":")
        host, container = host.strip(), container.strip() or host.strip()
        if not (PurePosixPath(host).is_absolute() and PurePosixPath(container).is_absolute()):
            raise ValueError(f"Shared dir paths must be absolute: '{entry}'")
        return cls(host=PurePosixPath(host), container=Path(container))


class Settings(BaseSettings):
    """Service-wide settings loaded from environment variables.

    Environment variables are prefixed with ``SOS_FFS_``,
    e.g. ``SOS_FFS_MAPPINGS_DIR``.
    """

    model_config = SettingsConfigDict(env_prefix="SOS_FFS_")

    mappings_dir: Path = Path("mappings")
    app_name: str = "SOS File Format Service"
    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8000
    # Comma-separated ``host_path[:container_path]`` entries. Files below these
    # directories can be validated in place via ``/validate/local``; empty
    # disables that endpoint. Paths containing ``:`` or ``,`` are not supported.
    shared_dirs: Annotated[list[SharedDir], NoDecode] = []

    @field_validator("shared_dirs", mode="before")
    @classmethod
    def _parse_shared_dirs(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [SharedDir.parse(entry) for entry in value.split(",") if entry.strip()]
        return value
