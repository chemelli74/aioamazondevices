"""aioamazondevices library."""

<<<<<<< HEAD
<<<<<<< HEAD
__version__ = "3.3.1"
=======
__version__ = "3.2.0-rc.1"
>>>>>>> cd29f58 (3.2.0-rc.1)
=======
__version__ = "3.1.19"
>>>>>>> 879e3af (chore: merge)


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
