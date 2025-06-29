"""aioamazondevices library."""

<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
__version__ = "3.3.1"
=======
__version__ = "3.2.0-rc.1"
>>>>>>> cd29f58 (3.2.0-rc.1)
=======
__version__ = "3.1.19"
>>>>>>> 879e3af (chore: merge)
=======
__version__ = "3.2.0-rc.1"
>>>>>>> 7a3342a (3.2.0-rc.1)
=======
__version__ = "3.2.0-rc.2"
>>>>>>> 36d63fb (3.2.0-rc.2)
=======
__version__ = "3.2.0-rc.3"
>>>>>>> fa9ac98 (3.2.0-rc.3)


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
