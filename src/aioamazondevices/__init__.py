"""aioamazondevices library."""

__version__ = "14.1.0"


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
