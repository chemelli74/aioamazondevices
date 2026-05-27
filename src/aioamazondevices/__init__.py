"""aioamazondevices library."""

__version__ = "13.8.1"


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
