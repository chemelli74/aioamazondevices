"""aioamazondevices library."""

__version__ = "13.7.2"


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
