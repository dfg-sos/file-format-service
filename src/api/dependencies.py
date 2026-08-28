"""FastAPI dependency-injection wiring.

Provides singleton instances of settings, services, and utilities so that
routers can receive them via ``Depends`` without manual construction.
"""

from functools import lru_cache
from pathlib import Path

from format_validator import FormatTranslator

from config import Settings
from service.compatibility_service import CompatibilityService


@lru_cache
def get_settings() -> Settings:
    """Return cached service settings."""
    return Settings()


@lru_cache
def get_format_translator() -> FormatTranslator:
    """Return cached ``FormatTranslator`` loaded from the configured directory."""
    settings = get_settings()
    return FormatTranslator(settings.mappings_dir)


@lru_cache
def get_compatibility_service() -> CompatibilityService:
    """Return cached ``CompatibilityService`` with the loaded ontology."""
    settings = get_settings()
    return CompatibilityService(settings)


def get_file_storage_path() -> Path:
    """Return the directory where uploaded files are temporarily stored.

    In production this could be backed by S3 / volume mounts.
    """
    return Path("/tmp/sos_file_format_service/uploads")
