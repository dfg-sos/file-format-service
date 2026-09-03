"""Application configuration via pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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
