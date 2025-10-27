"""aioamazondevices library."""

__version__ = "6.5.5"


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
