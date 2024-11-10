"""Custom authentication module for httpx."""

import base64
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import (
    Any,
    cast,
)

import httpx
from httpx import Cookies
from pyasn1.codec.der import decoder
from pyasn1.type import namedtype, univ
from rsa import PrivateKey, pkcs1

from .const import _LOGGER, AMAZON_APP_NAME, AMAZON_APP_VERSION
from .exceptions import (
    AuthFlowError,
    AuthMissingAccessToken,
    AuthMissingRefreshToken,
    AuthMissingSigningData,
    AuthMissingTimestamp,
    AuthMissingWebsiteCookies,
)


def base64_der_to_pkcs1(base64_key: str) -> str:
    """Convert DER private key to PEM format."""

    class PrivateKeyAlgorithm(univ.Sequence):  # type: ignore[misc]
        component_type = namedtype.NamedTypes(
            namedtype.NamedType("algorithm", univ.ObjectIdentifier()),
            namedtype.NamedType("parameters", univ.Any()),
        )

    class PrivateKeyInfo(univ.Sequence):  # type: ignore[misc]
        component_type = namedtype.NamedTypes(
            namedtype.NamedType("version", univ.Integer()),
            namedtype.NamedType("pkalgo", PrivateKeyAlgorithm()),
            namedtype.NamedType("key", univ.OctetString()),
        )

    encoded_key = base64.b64decode(base64_key)
    (key_info, _) = decoder.decode(encoded_key, asn1Spec=PrivateKeyInfo())
    key_octet_string = key_info.components[2]
    key = PrivateKey.load_pkcs1(key_octet_string, format="DER")
    return cast(str, key.save_pkcs1().decode("utf-8"))


def refresh_access_token(
    refresh_token: str,
    domain: str,
) -> dict[str, Any]:
    """Refresh an access token."""
    body = {
        "app_name": AMAZON_APP_NAME,
        "app_version": AMAZON_APP_VERSION,
        "source_token": refresh_token,
        "requested_token_type": "access_token",
        "source_token_type": "refresh_token",
    }

    resp = httpx.post(f"https://api.amazon.{domain}/auth/token", data=body)
    resp.raise_for_status()
    resp_dict = resp.json()

    expires_in_sec = int(resp_dict["expires_in"])
    expires = (datetime.now(UTC) + timedelta(seconds=expires_in_sec)).timestamp()

    return {"access_token": resp_dict["access_token"], "expires": expires}


def refresh_website_cookies(
    refresh_token: str,
    domain: str,
) -> dict[str, str]:
    """Fetch website cookies for a specific domain."""
    url = f"https://www.amazon.{domain}/ap/exchangetoken/cookies"

    body = {
        "app_name": AMAZON_APP_NAME,
        "app_version": AMAZON_APP_VERSION,
        "source_token": refresh_token,
        "requested_token_type": "auth_cookies",
        "source_token_type": "refresh_token",
        "domain": f".amazon.{domain}",
    }

    resp = httpx.post(url, data=body)
    resp.raise_for_status()
    resp_dict = resp.json()

    raw_cookies = resp_dict["response"]["tokens"]["cookies"]
    website_cookies = {}
    for domain_cookies in raw_cookies:
        for cookie in raw_cookies[domain_cookies]:
            website_cookies[cookie["Name"]] = cookie["Value"].replace(r'"', r"")

    return website_cookies


def user_profile(access_token: str, domain: str) -> dict[str, Any]:
    """Return Amazon user profile from Amazon."""
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = httpx.get(f"https://api.amazon.{domain}/user/profile", headers=headers)
    resp.raise_for_status()
    profile: dict[str, Any] = resp.json()

    if "user_id" not in profile:
        raise ValueError("Malformed user profile response.")

    return profile


def sign_request(
    method: str,
    path: str,
    body: bytes,
    adp_token: str,
    private_key: str,
) -> dict[str, str]:
    """Create signed headers for http requests."""
    date = datetime.now(UTC).isoformat("T") + "Z"
    str_body = body.decode("utf-8")

    data = f"{method}\n{path}\n{date}\n{str_body}\n{adp_token}"

    key = PrivateKey.load_pkcs1(private_key.encode("utf-8"))
    cipher = pkcs1.sign(data.encode(), key, "SHA-256")
    signed_encoded = base64.b64encode(cipher)

    signature = f"{signed_encoded.decode()}:{date}"

    return {
        "x-adp-token": adp_token,
        "x-adp-alg": "SHA256withRSA:1.0",
        "x-adp-signature": signature,
    }


class Authenticator(httpx.Auth):  # type: ignore[misc]
    """Amazon Authenticator class."""

    access_token: str | None = None
    activation_bytes: str | None = None
    adp_token: str | None = None
    customer_info: dict[str, Any] | None = None
    device_info: dict[str, Any] | None = None
    device_private_key: str | None = None
    expires: float | None = None
    domain: str
    refresh_token: str | None = None
    store_authentication_cookie: dict[str, Any] | None = None
    website_cookies: dict[str, Any] | None = None
    requires_request_body: bool = True
    _forbid_new_attrs: bool = True
    _apply_test_convert: bool = True

    def update_attrs(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Update attributes from dict."""
        for attr, value in kwargs.items():
            setattr(self, attr, value)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        domain: str,
    ) -> "Authenticator":
        """Instantiate an Authenticator from authentication dictionary."""
        auth = cls()

        auth.domain = domain

        if "login_cookies" in data:
            auth.website_cookies = data.pop("login_cookies")

        if data["device_private_key"].startswith("MII"):
            pk_der = data["device_private_key"]
            data["device_private_key"] = base64_der_to_pkcs1(pk_der)

        auth.update_attrs(**data)

        _LOGGER.info("load data from dictionary for domain %s", auth.domain)

        return auth

    def auth_flow(
        self,
        request: httpx.Request,
    ) -> Generator[httpx.Request, httpx.Response, None]:
        """Auth flow to be executed on every request by :mod:`httpx`."""
        available_modes = self.available_auth_modes

        _LOGGER.debug("Auth flow modes: %s", available_modes)
        if "signing" in available_modes:
            self._apply_signing_auth_flow(request)
        elif "bearer" in available_modes:
            self._apply_bearer_auth_flow(request)
        else:
            message = "signing or bearer auth flow are not available."
            _LOGGER.critical(message)
            raise AuthFlowError(message)

        yield request

    def _apply_signing_auth_flow(self, request: httpx.Request) -> None:
        if self.adp_token is None or self.device_private_key is None:
            raise AuthMissingSigningData

        headers = sign_request(
            method=request.method,
            path=request.url.raw_path.decode(),
            body=request.content,
            adp_token=self.adp_token,
            private_key=self.device_private_key,
        )

        request.headers.update(headers)
        _LOGGER.info("signing auth flow applied to request")

    def _apply_bearer_auth_flow(self, request: httpx.Request) -> None:
        if self.access_token_expired:
            self.refresh_access_token()

        if self.access_token is None:
            raise AuthMissingAccessToken

        headers = {"Authorization": "Bearer " + self.access_token, "client-id": "0"}
        request.headers.update(headers)
        _LOGGER.info("bearer auth flow applied to request")

    def _apply_cookies_auth_flow(self, request: httpx.Request) -> None:
        if self.website_cookies is None:
            raise AuthMissingWebsiteCookies
        cookies = self.website_cookies.copy()

        Cookies(cookies).set_cookie_header(request)
        _LOGGER.info("cookies auth flow applied to request")

    @property
    def available_auth_modes(self) -> list[str]:
        """List available authentication modes."""
        available_modes = []

        if self.adp_token and self.device_private_key:
            available_modes.append("signing")

        if self.access_token:
            if self.access_token_expired and not self.refresh_token:
                pass
            else:
                available_modes.append("bearer")

        if self.website_cookies:
            available_modes.append("cookies")

        return available_modes

    def refresh_access_token(self, force: bool = False) -> None:
        """Refresh access token."""
        if force or self.access_token_expired:
            if self.refresh_token is None:
                message = "No refresh token found. Can't refresh access token."
                _LOGGER.critical(message)
                raise AuthMissingRefreshToken(message)

            refresh_data = refresh_access_token(
                refresh_token=self.refresh_token,
                domain=self.domain,
            )

            self.update_attrs(**refresh_data)
        else:
            _LOGGER.info(
                "Access Token not expired. No refresh necessary. "
                "To force refresh please use force=True",
            )

    def set_website_cookies_for_country(self) -> None:
        """Set website cookies for country."""
        if self.refresh_token is None:
            raise AuthMissingRefreshToken

        self.website_cookies = refresh_website_cookies(
            self.refresh_token,
            self.domain,
        )

    def user_profile(self) -> dict[str, Any]:
        """Get user profile."""
        if self.access_token is None:
            raise AuthMissingAccessToken

        return user_profile(access_token=self.access_token, domain=self.domain)

    @property
    def access_token_expires(self) -> timedelta:
        """Time to access token expiration."""
        if self.expires is None:
            raise AuthMissingTimestamp
        return datetime.fromtimestamp(self.expires, UTC) - datetime.now(
            UTC,
        )

    @property
    def access_token_expired(self) -> bool:
        """Return True if access token is expired."""
        if self.expires is None:
            raise AuthMissingTimestamp
        return datetime.fromtimestamp(self.expires, UTC) <= datetime.now(
            UTC,
        )
