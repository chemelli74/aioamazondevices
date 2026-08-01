# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Base tests for aioamazondevices."""

from aioamazondevices.api import (
    AmazonEchoApi,
)
from aioamazondevices.exceptions import (
    CannotAuthenticate,
    CannotConnect,
)


def test_objects_can_be_imported() -> None:
    """Verify objects exist."""
    assert type(AmazonEchoApi)
    assert type(CannotConnect)
    assert type(CannotAuthenticate)
