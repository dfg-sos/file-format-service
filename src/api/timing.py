"""Measure the steps of a request for the ``Server-Timing`` response header."""

import time
from collections.abc import Iterator
from contextlib import contextmanager


class ServerTiming:
    """Durations of named steps, formatted as a ``Server-Timing`` header value.

    Usage::

        timing = ServerTiming()
        with timing("validate"):
            ...
        response.headers["Server-Timing"] = str(timing)   # "validate;dur=12.3"
    """

    def __init__(self) -> None:
        self._durations_ms: dict[str, float] = {}

    @contextmanager
    def __call__(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self._durations_ms[name] = (time.perf_counter() - start) * 1000

    def __str__(self) -> str:
        return ", ".join(f"{name};dur={ms:.1f}" for name, ms in self._durations_ms.items())
