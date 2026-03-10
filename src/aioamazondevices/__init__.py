"""aioamazondevices library."""

__version__ = "13.0.0"


from .api import AmazonEchoApi
from .exceptions import (
    CannotAuthenticate,
    CannotConnect,
)
from .structures import AmazonDevice, AmazonMediaControls

__all__ = [
    "AmazonDevice",
    "AmazonEchoApi",
    "AmazonMediaControls",
    "CannotAuthenticate",
    "CannotConnect",
]
