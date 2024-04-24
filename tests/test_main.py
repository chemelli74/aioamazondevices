"""Base tests for aioamazondevices."""

from aioamazondevices.main import add

SUM = 2


def test_add() -> None:
    """Adding two number works as expected."""
    assert add(1, 1) == SUM
