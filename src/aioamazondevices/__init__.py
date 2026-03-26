"""aioamazondevices library."""

__version__ = "13.3.1"


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
