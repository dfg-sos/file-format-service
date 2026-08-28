"""Pydantic schemas for the ``/validate`` endpoint."""

from pydantic import BaseModel


class ValidationEvent(BaseModel):
    """A single event (error, warning, or info) emitted during validation."""

    message: str
    timestamp: str
    severity: str
    cause: str | None = None


class ValidationResponse(BaseModel):
    """Response returned by the validation endpoint.

    The ``valid`` flag is ``True`` only when the validation status is
    ``SUCCESS``. Both ``FAILURE`` and ``UNCERTAIN`` yield ``valid=False``.
    """

    status: str
    valid: bool
    errors: list[ValidationEvent]
    warnings: list[ValidationEvent]
    infos: list[ValidationEvent]
