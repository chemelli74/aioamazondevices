"""Comelit SimpleHome library exceptions."""

from __future__ import annotations


class AmazonError(Exception):
    """Base class for aioamazondevices errors."""


class CannotConnect(AmazonError):
    """Exception raised when connection fails."""


class CannotAuthenticate(AmazonError):
    """Exception raised when credentials are incorrect."""


class CannotRetrieveData(AmazonError):
    """Exception raised when data retrieval fails."""


class CannotRegisterDevice(AmazonError):
    """Exception raised when device registration fails."""


class WrongMethod(AmazonError):
    """Exception raised when the wrong login metho is used."""


class WrongCountry(AmazonError):
    """Exceptio nraised when Amazon country."""
