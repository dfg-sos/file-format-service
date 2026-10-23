"""Expected-metadata parsing, keyed by the validator of a format.

The service passes the client's ``expected_metadata`` map through without
knowing its keys; the validator selected for the format decides which keys it
understands and builds its metadata sidecar from them.

Transitional: ``format_validator`` does not expose this yet. Once it ships
``supported_metadata_keys`` and ``parse_metadata``, import them from there and
delete this module. Until then, the knowledge of the EO sidecar is kept here
and nowhere else in the service.
"""

from collections.abc import Mapping
from pathlib import Path

from format_validator import (
    EOFileFormatValidator,
    EOMetadata,
    FileFormatValidator,
    FileInput,
    FormatIdentifier,
    ValidationMode,
    ValidationRequest,
    VectorFileValidator,
    registry,
)


class UnsupportedMetadataKeys(ValueError):
    """Keys the format's validator does not understand."""

    def __init__(self, unknown: set[str], supported: frozenset[str]):
        self.unknown = unknown
        self.supported = supported
        super().__init__(
            f"Unsupported expected_metadata key(s) {sorted(unknown)}; supported for this format: {sorted(supported)}"
        )


def _validator(format_id: FormatIdentifier) -> FileFormatValidator | None:
    # The registry only selects validators by request, so a placeholder request is built.
    probe = ValidationRequest(format_id, FileInput(Path()), ValidationMode.BASIC)
    return registry.choose_and_instantiate(probe)


def _metadata_keys(validator: FileFormatValidator | None) -> frozenset[str]:
    if isinstance(validator, VectorFileValidator):
        return frozenset({"crs", "geometry_type"})
    if isinstance(validator, EOFileFormatValidator):
        return frozenset({"crs"})
    return frozenset()


def supported_metadata_keys(format_id: FormatIdentifier) -> frozenset[str]:
    """Keys of ``expected_metadata`` the validator of ``format_id`` understands."""
    return _metadata_keys(_validator(format_id))


def parse_metadata(format_id: FormatIdentifier, values: Mapping[str, str]) -> object | None:
    """Build the metadata sidecar for ``format_id`` from ``values``.

    Returns ``None`` when the validator takes no metadata. Without values the
    sidecar is empty, so the validator reports the checks it skips.

    Raises:
        UnsupportedMetadataKeys: A key is not understood by the format's validator.
        ValueError: A value cannot be parsed (e.g. an unknown CRS).
    """
    validator = _validator(format_id)
    supported = _metadata_keys(validator)
    unknown = set(values) - supported
    if unknown:
        raise UnsupportedMetadataKeys(unknown, supported)
    if not supported:
        return None
    # Every validator with metadata keys is an EO validator so far.
    return EOMetadata.from_strings(crs=values.get("crs"), geometry_type=values.get("geometry_type"))
