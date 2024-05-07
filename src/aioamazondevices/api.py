"""Support for Amazon devices."""

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import orjson
from bs4 import BeautifulSoup, Tag
from httpx import AsyncClient, Response

from .const import (
    _LOGGER,
    AMAZON_APP_BUNDLE_ID,
    AMAZON_APP_ID,
    AMAZON_APP_VERSION,
    AMAZON_SERIAL_NUMBER,
    AMAZON_SOFTWARE_VERSION,
    DEFAULT_HEADERS,
    DOMAIN_BY_COUNTRY,
    URI_QUERIES,
)
from .exceptions import CannotAuthenticate


@dataclass
class AmazonDevice:
    """Amazon device class."""

    connected: bool
    connection_type: str
    ip_address: str
    name: str
    mac: str
    type: str
    wifi: str


def _build_init_cookies() -> dict[str, str]:
    """Build initial cookies to prevent captcha in most cases."""
    token_bytes = secrets.token_bytes(313)
    frc = base64.b64encode(token_bytes).decode("ascii").rstrip("=")

    map_md_dict = {
        "device_user_dictionary": [],
        "device_registration_data": {
            "software_version": AMAZON_SOFTWARE_VERSION,
        },
        "app_identifier": {
            "app_version": AMAZON_APP_VERSION,
            "bundle_id": AMAZON_APP_BUNDLE_ID,
        },
    }
    map_md_str = orjson.dumps(map_md_dict).decode("utf-8")
    map_md = base64.b64encode(map_md_str.encode()).decode().rstrip("=")

    return {"frc": frc, "map-md": map_md, "amzn-app-id": AMAZON_APP_ID}


class AmazonEchoApi:
    """Queries Amazon for Echo devices."""

    def __init__(
        self,
        login_country_code: str,
        login_email: str,
        login_password: str,
    ) -> None:
        """Initialize the scanner."""
        locale = DOMAIN_BY_COUNTRY.get(login_country_code)
        domain = locale["domain"] if locale else login_country_code

        assoc_handle = "amzn_dp_project_dee_ios"
        if not locale:
            assoc_handle += f"_{login_country_code}"
        self._assoc_handle = assoc_handle

        self._login_email = login_email
        self._login_password = login_password
        self._domain = domain
        self._url = f"https://www.amazon.{domain}"
        self._cookies = _build_init_cookies()
        self._headers = DEFAULT_HEADERS

        self.session: AsyncClient

    def _create_code_verifier(self, length: int = 32) -> bytes:
        """Create code verifier."""
        verifier = secrets.token_bytes(length)
        return base64.urlsafe_b64encode(verifier).rstrip(b"=")

    def _create_s256_code_challenge(self, verifier: bytes) -> bytes:
        """Create S256 code challenge."""
        m = hashlib.sha256(verifier)
        return base64.urlsafe_b64encode(m.digest()).rstrip(b"=")

    def _build_client_id(self) -> str:
        """Build client ID."""
        serial = uuid.uuid4().hex.upper()
        client_id = serial.encode() + AMAZON_SERIAL_NUMBER
        return client_id.hex()

    def _build_oauth_url(
        self,
    ) -> str:
        """Build the url to login to Amazon as a Mobile device."""
        client_id = self._build_client_id()
        code_challenge = self._create_s256_code_challenge(self._create_code_verifier())

        oauth_params = {
            "openid.oa2.response_type": "code",
            "openid.oa2.code_challenge_method": "S256",
            "openid.oa2.code_challenge": code_challenge,
            "openid.return_to": f"https://www.amazon.{self._domain}/ap/maplanding",
            "openid.assoc_handle": self._assoc_handle,
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "accountStatusPolicy": "P1",
            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.mode": "checkid_setup",
            "openid.ns.oa2": "http://www.amazon.com/ap/ext/oauth/2",
            "openid.oa2.client_id": f"device:{client_id}",
            "openid.ns.pape": "http://specs.openid.net/extensions/pape/1.0",
            "openid.oa2.scope": "device_auth_access",
            "forceMobileLayout": "true",
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.pape.max_auth_age": "0",
        }

        return f"https://www.amazon.{self._domain}/ap/signin?{urlencode(oauth_params)}"

    def _get_inputs_from_soup(self, soup: BeautifulSoup) -> dict[str, str]:
        """Extract hidden form input fields from a Amazon login page."""
        form = soup.find("form", {"name": "signIn"}) or soup.find("form")

        if not isinstance(form, Tag):
            raise TypeError("No form found in page or something other is going wrong.")

        inputs = {}
        for field in form.find_all("input"):
            if field.get("type") and field["type"] == "hidden":
                inputs[field["name"]] = field.get("value", "")

        return inputs

    def _get_request_from_soup(self, soup: BeautifulSoup) -> tuple[str, str]:
        """Extract URL and method for the next request."""
        _LOGGER.debug("Get request data from HTML source")
        form = soup.find("form")
        if isinstance(form, Tag):
            method = form["method"]
            url = form["action"]
            if isinstance(method, str) and isinstance(url, str):
                return method, url
        raise TypeError("Unable to extract form data from response.")

    def _client_session(self) -> None:
        """Create httpx ClientSession."""
        if not hasattr(self, "session") or self.session.is_closed:
            _LOGGER.debug("Creating HTTP ClientSession")
            self.session = AsyncClient(
                base_url=f"https://www.amazon.{self._domain}",
                headers=DEFAULT_HEADERS,
                cookies=self._cookies,
                follow_redirects=True,
            )

    async def _session_request(
        self,
        method: str,
        url: str,
        input_data: dict[str, Any] | None = None,
    ) -> tuple[BeautifulSoup, Response]:
        """Return request response context data."""
        _LOGGER.debug("%s request: %s with payload %s", method, url, input_data)
        resp = await self.session.request(
            method,
            url,
            data=input_data,
        )
        return BeautifulSoup(resp.content, "html.parser"), resp

    async def login(self, otp_code: str) -> bool:
        """Login to Amazon."""
        _LOGGER.debug("Logging-in for %s [otp code %s]", self._login_email, otp_code)
        self._client_session()

        _LOGGER.debug("Build oauth URL")
        login_url = self._build_oauth_url()

        login_soup, _ = await self._session_request("GET", login_url)
        login_method, login_url = self._get_request_from_soup(login_soup)
        login_inputs = self._get_inputs_from_soup(login_soup)
        login_inputs["email"] = self._login_email
        login_inputs["password"] = self._login_password

        login_soup, _ = await self._session_request(
            login_method,
            login_url,
            login_inputs,
        )

        if not login_soup.find("input", id="auth-mfa-otpcode"):
            _LOGGER.debug('Cannot find "auth-mfa-otpcode" in html source')
            raise CannotAuthenticate

        login_method, login_url = self._get_request_from_soup(login_soup)

        login_inputs = self._get_inputs_from_soup(login_soup)
        login_inputs["otpCode"] = otp_code
        login_inputs["mfaSubmit"] = "Submit"
        login_inputs["rememberDevice"] = "false"

        login_soup, login_resp = await self._session_request(
            login_method,
            login_url,
            login_inputs,
        )

        authcode_url = None
        _LOGGER.debug("Login query: %s", login_resp.url.query)
        if b"openid.oa2.authorization_code" in login_resp.url.query:
            authcode_url = login_resp.url
        elif len(login_resp.history) > 0:
            for history in login_resp.history:
                if b"openid.oa2.authorization_code" in history.url.query:
                    authcode_url = history.url
                    break

        if authcode_url is None:
            raise CannotAuthenticate

        return True

    async def close(self) -> None:
        """Close httpx session."""
        if hasattr(self, "session"):
            _LOGGER.debug("Closing httpx session")
            await self.session.aclose()

    async def get_devices_data(
        self,
    ) -> dict[str, Any]:
        """Get Amazon devices data."""
        devices = {}
        for key in URI_QUERIES:
            _, raw_resp = await self._session_request(
                "GET",
                f"https://alexa.amazon.{self._domain}{URI_QUERIES[key]}",
            )

            devices.update(
                {
                    key: orjson.loads(
                        raw_resp.text,
                    ),
                },
            )

        return devices
