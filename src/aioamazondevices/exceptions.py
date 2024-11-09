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


class AuthFlowError(AmazonError):
    """Exception raised when auth flow fails."""


class AuthMissingTimestamp(AmazonError):
    """Exception raised when expires timestamp is missing."""


class AuthMissingAccessToken(AmazonError):
    """Exception raised when access token is missing."""


class AuthMissingRefreshToken(AmazonError):
    """Exception raised when refresh token is missing."""


class AuthMissingSigningData(AmazonError):
    """Exception raised when some data for signing are missing."""


class AuthMissingWebsiteCookies(AmazonError):
    """Exception raised when website cookies are missing."""
