"""aioamazondevices library."""

__version__ = "3.0.4"


from .api import AmazonDevice, AmazonEchoApi
from .exceptions import (
    CannotAuthenticate,
    CannotConnect,
)

__all__ = [
    "AmazonDevice",
    "AmazonEchoApi",
    "CannotAuthenticate",
    "CannotConnect",
]
