# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""aioamazondevices library."""

__version__ = "15.1.0"


from .api import AmazonEchoApi
from .exceptions import (
    CannotAuthenticate,
    CannotConnect,
)

__all__ = [
    "AmazonEchoApi",
    "CannotAuthenticate",
    "CannotConnect",
]
