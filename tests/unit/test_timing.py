"""Unit tests for ``ServerTiming``."""

import re

import pytest

from api.timing import ServerTiming


def test_steps_in_order() -> None:
    timing = ServerTiming()
    with timing("resolve"):
        pass
    with timing("validate"):
        pass
    assert re.fullmatch(r"resolve;dur=\d+\.\d, validate;dur=\d+\.\d", str(timing))


def test_step_recorded_when_it_raises() -> None:
    timing = ServerTiming()
    with pytest.raises(RuntimeError), timing("validate"):
        raise RuntimeError
    assert str(timing).startswith("validate;dur=")


def test_empty() -> None:
    assert str(ServerTiming()) == ""
