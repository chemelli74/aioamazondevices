"""aioamazondevices library."""

__version__ = "0.1.1"


from .api import AmazonDevice, AmazonEchoApi
from .exceptions import (
    CannotAuthenticate,
    CannotConnect,
)

__all__ = [
    "AmazonDevice",
    "AmazonEchoApi",
    "CannotConnect",
    "CannotAuthenticate",
]
