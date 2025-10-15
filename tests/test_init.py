"""Base tests for aioamazondevices."""

from aioamazondevices.api import (
    AmazonDevice,
    AmazonEchoApi,
)
from aioamazondevices.exceptions import (
    CannotAuthenticate,
    CannotConnect,
)


def test_objects_can_be_imported() -> None:
    """Verify objects exist."""
    assert type(AmazonDevice)
    assert type(AmazonEchoApi)
    assert type(CannotConnect)
    assert type(CannotAuthenticate)
