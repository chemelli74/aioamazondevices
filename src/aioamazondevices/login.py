"""Support for Amazon devices."""

import asyncio
import base64
import hashlib
import mimetypes
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPMethod, HTTPStatus
from http.cookies import Morsel
from typing import Any, cast
from urllib.parse import parse_qs, urlencode

import orjson
from aiohttp import (
    ClientConnectorError,
    ClientResponse,
    ClientSession,
    ContentTypeError,
)
from bs4 import BeautifulSoup, Tag
from multidict import MultiDictProxy
from yarl import URL

from . import __version__
from .const.common import (
    _LOGGER,
    AMAZON_APP_BUNDLE_ID,
    AMAZON_APP_ID,
    AMAZON_APP_NAME,
    AMAZON_APP_VERSION,
    AMAZON_CLIENT_OS,
    AMAZON_DEVICE_SOFTWARE_VERSION,
    AMAZON_DEVICE_TYPE,
    CSRF_COOKIE,
    DEFAULT_HEADERS,
    DEFAULT_SITE,
    HTTP_ERROR_199,
    HTTP_ERROR_299,
    REFRESH_ACCESS_TOKEN,
    REFRESH_AUTH_COOKIES,
    REQUEST_AGENT,
    URI_SIGNIN,
)
from .exceptions import (
    CannotAuthenticate,
    CannotConnect,
    CannotRegisterDevice,
    CannotRetrieveData,
    WrongMethod,
)
from .utils import country_specific_data, obfuscate_email, save_to_file, scrub_fields


class AmazonLogin:
    """Login and register to Amazon Alexa."""

    def __init__(
        self,
        client_session: ClientSession,
        login_email: str,
        login_password: str,
        login_data: dict[str, Any] | None = None,
        save_to_disk: bool = False,
    ) -> None:
        """Initialize the scanner."""
        # Check if there is a previous login, otherwise use default (US)
        site = login_data.get("site", DEFAULT_SITE) if login_data else DEFAULT_SITE
        _LOGGER.debug("Using site: %s", site)
        country_data = country_specific_data(site)
        self._domain = country_data["domain"]
        self._country_code = country_data["country"]
        self._language = country_data["language"]

        self._save_to_disk = save_to_disk

        self._csrf_cookie: str | None = None

        self._login_email = login_email
        self._login_password = login_password

        self._cookies = self._build_init_cookies()
        self._login_stored_data = login_data or {}
        self._serial = self._serial_number()

        self._session = client_session

        _LOGGER.debug("Initialize library v%s", __version__)

    @property
    def domain(self) -> str:
        """Return current Amazon domain."""
        return self._domain

    def _load_website_cookies(self) -> dict[str, str]:
        """Get website cookies, if avaliables."""
        if not self._login_stored_data:
            return {}

        website_cookies: dict[str, Any] = self._login_stored_data["website_cookies"]
        website_cookies.update(
            {
                "session-token": self._login_stored_data["store_authentication_cookie"][
                    "cookie"
                ]
            }
        )
        website_cookies.update({"lc-acbit": self._language})

        return website_cookies

    def _serial_number(self) -> str:
        """Get or calculate device serial number."""
        if not self._login_stored_data:
            # Create a new serial number
            _LOGGER.debug("Cannot find previous login data, creating new serial number")
            return uuid.uuid4().hex.upper()

        _LOGGER.debug("Found previous login data, loading serial number")
        return cast(
            "str",
            self._login_stored_data["device_info"]["device_serial_number"],
        )

    def _build_init_cookies(self) -> dict[str, str]:
        """Build initial cookies to prevent captcha in most cases."""
        token_bytes = secrets.token_bytes(313)
        frc = base64.b64encode(token_bytes).decode("ascii").rstrip("=")

        map_md_dict = {
            "device_user_dictionary": [],
            "device_registration_data": {
                "software_version": AMAZON_DEVICE_SOFTWARE_VERSION,
            },
            "app_identifier": {
                "app_version": AMAZON_APP_VERSION,
                "bundle_id": AMAZON_APP_BUNDLE_ID,
            },
        }
        map_md_str = orjson.dumps(map_md_dict).decode("utf-8")
        map_md = base64.b64encode(map_md_str.encode()).decode().rstrip("=")

        return {"amzn-app-id": AMAZON_APP_ID, "frc": frc, "map-md": map_md}

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
        client_id = self._serial.encode() + b"#" + AMAZON_DEVICE_TYPE.encode("utf-8")
        return client_id.hex()

    def _build_oauth_url(
        self,
        code_verifier: bytes,
        client_id: str,
    ) -> str:
        """Build the url to login to Amazon as a Mobile device."""
        code_challenge = self._create_s256_code_challenge(code_verifier)

        oauth_params = {
            "openid.return_to": "https://www.amazon.com/ap/maplanding",
            "openid.oa2.code_challenge_method": "S256",
            "openid.assoc_handle": "amzn_dp_project_dee_ios",
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "pageId": "amzn_dp_project_dee_ios",
            "accountStatusPolicy": "P1",
            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.mode": "checkid_setup",
            "openid.ns.oa2": "http://www.amazon.com/ap/ext/oauth/2",
            "openid.oa2.client_id": f"device:{client_id}",
            "language": self._language.replace("-", "_"),
            "openid.ns.pape": "http://specs.openid.net/extensions/pape/1.0",
            "openid.oa2.code_challenge": code_challenge,
            "openid.oa2.scope": "device_auth_access",
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.pape.max_auth_age": "0",
            "openid.oa2.response_type": "code",
        }

        return f"https://www.amazon.com{URI_SIGNIN}?{urlencode(oauth_params)}"

    def _get_inputs_from_soup(self, soup: BeautifulSoup) -> dict[str, str]:
        """Extract hidden form input fields from a Amazon login page."""
        form = soup.find("form", {"name": "signIn"}) or soup.find("form")

        if not isinstance(form, Tag):
            raise CannotAuthenticate("Unable to find form in login response")

        inputs = {}
        for field in form.find_all("input"):
            if isinstance(field, Tag) and field.get("type", "") == "hidden":
                inputs[field["name"]] = field.get("value", "")

        return inputs

    def _get_request_from_soup(self, soup: BeautifulSoup) -> tuple[str, str]:
        """Extract URL and method for the next request."""
        _LOGGER.debug("Get request data from HTML source")
        form = soup.find("form", {"name": "signIn"}) or soup.find("form")
        if isinstance(form, Tag):
            method = form.get("method")
            url = form.get("action")
            if isinstance(method, str) and isinstance(url, str):
                return method, url
        raise CannotAuthenticate("Unable to extract form data from response")

    def _extract_code_from_url(self, url: URL) -> str:
        """Extract the access token from url query after login."""
        parsed_url: dict[str, list[str]] = {}
        if isinstance(url.query, bytes):
            parsed_url = parse_qs(url.query.decode())
        elif isinstance(url.query, MultiDictProxy):
            for key, value in url.query.items():
                parsed_url[key] = [value]
        else:
            raise CannotAuthenticate(
                f"Unable to extract authorization code from url: {url}"
            )
        return parsed_url["openid.oa2.authorization_code"][0]

    async def _ignore_ap_signin_error(self, response: ClientResponse) -> bool:
        """Return true if error is due to signin endpoint."""
        # Endpoint URI_SIGNIN replies with error 404
        # but reports the needed parameters anyway
        if history := response.history:
            return (
                response.status == HTTPStatus.NOT_FOUND
                and URI_SIGNIN in history[0].request_info.url.path
            )
        return False

    async def _http_phrase_error(self, error: int) -> str:
        """Convert numeric error in human phrase."""
        if error == HTTP_ERROR_199:
            return "Miscellaneous Warning"

        if error == HTTP_ERROR_299:
            return "Miscellaneous Persistent Warning"

        return HTTPStatus(error).phrase

    async def _session_request(
        self,
        method: str,
        url: str,
        input_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        json_data: bool = False,
        agent: str = "Amazon",
    ) -> tuple[BeautifulSoup, ClientResponse]:
        """Return request response context data."""
        _LOGGER.debug(
            "%s request: %s with payload %s [json=%s]",
            method,
            url,
            scrub_fields(input_data) if input_data else None,
            json_data,
        )

        headers = DEFAULT_HEADERS.copy()
        headers.update({"User-Agent": REQUEST_AGENT[agent]})
        headers.update({"Accept-Language": self._language})

        if self._csrf_cookie:
            csrf = {CSRF_COOKIE: self._csrf_cookie}
            _LOGGER.debug("Adding to headers: %s", csrf)
            headers.update(csrf)

        if json_data:
            json_header = {"Content-Type": "application/json; charset=utf-8"}
            _LOGGER.debug("Adding to headers: %s", json_header)
            headers.update(json_header)

        _cookies = (
            self._load_website_cookies() if self._login_stored_data else self._cookies
        )
        self._session.cookie_jar.update_cookies(_cookies, URL(f"amazon.{self._domain}"))

        resp: ClientResponse | None = None
        for delay in [0, 1, 2, 5, 8, 12, 21]:
            if delay:
                _LOGGER.info(
                    "Sleeping for %s seconds before retrying API call to %s", delay, url
                )
                await asyncio.sleep(delay)

            try:
                resp = await self._session.request(
                    method,
                    URL(url, encoded=True),
                    data=input_data if not json_data else orjson.dumps(input_data),
                    headers=headers,
                )

            except (TimeoutError, ClientConnectorError) as exc:
                _LOGGER.warning("Connection error to %s: %s", url, repr(exc))
                raise CannotConnect(f"Connection error during {method}") from exc

            # Retry with a delay only for specific HTTP status
            # that can benefits of a back-off
            if resp.status not in [
                HTTPStatus.INTERNAL_SERVER_ERROR,
                HTTPStatus.SERVICE_UNAVAILABLE,
                HTTPStatus.TOO_MANY_REQUESTS,
            ]:
                break

        if resp is None:
            _LOGGER.error("No response received from %s", url)
            raise CannotConnect(f"No response received from {url}")

        if not self._csrf_cookie and (
            csrf := resp.cookies.get(CSRF_COOKIE, Morsel()).value
        ):
            self._csrf_cookie = csrf
            _LOGGER.debug("CSRF cookie value: <%s> [%s]", self._csrf_cookie, url)

        content_type: str = resp.headers.get("Content-Type", "")
        _LOGGER.debug(
            "Response for url %s :\nstatus      : %s \
                                  \ncontent type: %s ",
            url,
            resp.status,
            content_type,
        )

        if resp.status != HTTPStatus.OK:
            if resp.status in [
                HTTPStatus.FORBIDDEN,
                HTTPStatus.PROXY_AUTHENTICATION_REQUIRED,
                HTTPStatus.UNAUTHORIZED,
            ]:
                raise CannotAuthenticate(await self._http_phrase_error(resp.status))
            if not await self._ignore_ap_signin_error(resp):
                raise CannotRetrieveData(
                    f"Request failed: {await self._http_phrase_error(resp.status)}"
                )

        if self._save_to_disk:
            await save_to_file(
                await resp.text(),
                url,
                mimetypes.guess_extension(content_type.split(";")[0]) or ".raw",
            )

        return BeautifulSoup(await resp.read() or "", "html.parser"), resp

    async def _register_device(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Register a dummy Alexa device."""
        authorization_code: str = data["authorization_code"]
        code_verifier: bytes = data["code_verifier"]

        body = {
            "requested_extensions": ["device_info", "customer_info"],
            "cookies": {"website_cookies": [], "domain": f".amazon.{self._domain}"},
            "registration_data": {
                "domain": "Device",
                "app_version": AMAZON_APP_VERSION,
                "device_type": AMAZON_DEVICE_TYPE,
                "device_name": (
                    f"%FIRST_NAME%\u0027s%DUPE_STRATEGY_1ST%{AMAZON_APP_NAME}"
                ),
                "os_version": AMAZON_CLIENT_OS,
                "device_serial": self._serial,
                "device_model": "iPhone",
                "app_name": AMAZON_APP_NAME,
                "software_version": AMAZON_DEVICE_SOFTWARE_VERSION,
            },
            "auth_data": {
                "use_global_authentication": "true",
                "client_id": self._build_client_id(),
                "authorization_code": authorization_code,
                "code_verifier": code_verifier.decode(),
                "code_algorithm": "SHA-256",
                "client_domain": "DeviceLegacy",
            },
            "user_context_map": {"frc": self._cookies["frc"]},
            "requested_token_type": [
                "bearer",
                "mac_dms",
                "website_cookies",
                "store_authentication_cookie",
            ],
        }

        register_url = "https://api.amazon.com/auth/register"
        _, raw_resp = await self._session_request(
            method=HTTPMethod.POST,
            url=register_url,
            input_data=body,
            json_data=True,
        )
        resp_json = await self._response_to_json(raw_resp)

        if raw_resp.status != HTTPStatus.OK:
            msg = resp_json["response"]["error"]["message"]
            _LOGGER.error(
                "Cannot register device for %s: %s",
                obfuscate_email(self._login_email),
                msg,
            )
            raise CannotRegisterDevice(
                f"{await self._http_phrase_error(raw_resp.status)}: {msg}"
            )

        success_response = resp_json["response"]["success"]

        tokens = success_response["tokens"]
        adp_token = tokens["mac_dms"]["adp_token"]
        device_private_key = tokens["mac_dms"]["device_private_key"]
        store_authentication_cookie = tokens["store_authentication_cookie"]
        access_token = tokens["bearer"]["access_token"]
        refresh_token = tokens["bearer"]["refresh_token"]
        expires_s = int(tokens["bearer"]["expires_in"])
        expires = (datetime.now(UTC) + timedelta(seconds=expires_s)).timestamp()

        extensions = success_response["extensions"]
        device_info = extensions["device_info"]
        customer_info = extensions["customer_info"]

        website_cookies = {}
        for cookie in tokens["website_cookies"]:
            website_cookies[cookie["Name"]] = cookie["Value"].replace(r'"', r"")

        login_data = {
            "adp_token": adp_token,
            "device_private_key": device_private_key,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires": expires,
            "website_cookies": website_cookies,
            "store_authentication_cookie": store_authentication_cookie,
            "device_info": device_info,
            "customer_info": customer_info,
        }
        _LOGGER.info("Register device: %s", scrub_fields(login_data))
        return login_data

    async def _response_to_json(self, raw_resp: ClientResponse) -> dict[str, Any]:
        """Convert response to JSON, if possible."""
        try:
            data = await raw_resp.json(loads=orjson.loads)
            if not data:
                _LOGGER.warning("Empty JSON data received")
                data = {}
            return cast("dict[str, Any]", data)
        except ContentTypeError as exc:
            raise ValueError("Response not in JSON format") from exc
        except orjson.JSONDecodeError as exc:
            raise ValueError("Response with corrupted JSON format") from exc

    async def login_mode_interactive(self, otp_code: str) -> dict[str, Any]:
        """Login to Amazon interactively via OTP."""
        _LOGGER.debug(
            "Logging-in for %s [otp code: %s]",
            obfuscate_email(self._login_email),
            bool(otp_code),
        )

        device_login_data = await self._login_mode_interactive_oauth(otp_code)

        login_data = await self._register_device(device_login_data)
        self._login_stored_data = login_data

        await self._domain_refresh_auth_cookies()

        self._login_stored_data.update({"site": f"https://www.amazon.{self._domain}"})
        # Can take a little while to register device but we need it
        # to be able to pickout account customer ID
        await asyncio.sleep(2)

        return self._login_stored_data

    async def _login_mode_interactive_oauth(
        self, otp_code: str
    ) -> dict[str, str | bytes]:
        """Login interactive via oauth URL."""
        code_verifier = self._create_code_verifier()
        client_id = self._build_client_id()

        _LOGGER.debug("Build oauth URL")
        login_url = self._build_oauth_url(code_verifier, client_id)

        login_soup, _ = await self._session_request(
            method=HTTPMethod.GET, url=login_url
        )
        login_method, login_url = self._get_request_from_soup(login_soup)
        login_inputs = self._get_inputs_from_soup(login_soup)
        login_inputs["email"] = self._login_email
        login_inputs["password"] = self._login_password

        _LOGGER.debug("Register at %s", login_url)
        login_soup, _ = await self._session_request(
            method=login_method,
            url=login_url,
            input_data=login_inputs,
        )

        if not login_soup.find("input", id="auth-mfa-otpcode"):
            _LOGGER.debug(
                'Cannot find "auth-mfa-otpcode" in html source [%s]', login_url
            )
            raise CannotAuthenticate("MFA OTP code not found on login page")

        login_method, login_url = self._get_request_from_soup(login_soup)

        login_inputs = self._get_inputs_from_soup(login_soup)
        login_inputs["otpCode"] = otp_code
        login_inputs["mfaSubmit"] = "Submit"
        login_inputs["rememberDevice"] = "false"

        login_soup, login_resp = await self._session_request(
            method=login_method,
            url=login_url,
            input_data=login_inputs,
        )
        _LOGGER.debug("Login response url:%s", login_resp.url)

        authcode = self._extract_code_from_url(login_resp.url)
        _LOGGER.debug("Login extracted authcode: %s", authcode)

        return {
            "authorization_code": authcode,
            "code_verifier": code_verifier,
            "domain": self._domain,
        }

    async def login_mode_stored_data(self) -> dict[str, Any]:
        """Login to Amazon using previously stored data."""
        if not self._login_stored_data:
            _LOGGER.debug(
                "Cannot find previous login data,\
                    use login_mode_interactive() method instead",
            )
            raise WrongMethod

        _LOGGER.debug(
            "Logging-in for %s with stored data",
            obfuscate_email(self._login_email),
        )

        # Check if session is still authenticated
        if not await self.auth_check_status():
            raise CannotAuthenticate("Session no longer authenticated")

        return self._login_stored_data

    async def _get_alexa_domain(self) -> str:
        """Get the Alexa domain."""
        _LOGGER.debug("Retrieve Alexa domain")
        _, raw_resp = await self._session_request(
            method=HTTPMethod.GET,
            url=f"https://alexa.amazon.{self._domain}/api/welcome",
        )
        json_data = await self._response_to_json(raw_resp)
        return cast(
            "str", json_data.get("alexaHostName", f"alexa.amazon.{self._domain}")
        )

    async def _refresh_auth_cookies(self) -> None:
        """Refresh cookies after domain swap."""
        _, json_token_resp = await self._refresh_data(REFRESH_AUTH_COOKIES)

        # Need to take cookies from response and create them as cookies
        website_cookies = self._login_stored_data["website_cookies"] = {}
        self._session.cookie_jar.clear()

        cookie_json = json_token_resp["response"]["tokens"]["cookies"]
        for cookie_domain in cookie_json:
            for cookie in cookie_json[cookie_domain]:
                new_cookie_value = cookie["Value"].replace(r'"', r"")
                new_cookie = {cookie["Name"]: new_cookie_value}
                self._session.cookie_jar.update_cookies(new_cookie, URL(cookie_domain))
                website_cookies.update(new_cookie)
                if cookie["Name"] == "session-token":
                    self._login_stored_data["store_authentication_cookie"] = {
                        "cookie": new_cookie_value
                    }

    async def _domain_refresh_auth_cookies(self) -> None:
        """Refresh cookies after domain swap."""
        _LOGGER.debug("Refreshing auth cookies after domain change")

        # Get the new Alexa domain
        user_domain = (await self._get_alexa_domain()).replace("alexa", "https://www")
        if user_domain != DEFAULT_SITE:
            _LOGGER.debug("User domain changed to %s", user_domain)
            country_data = country_specific_data(user_domain)
            self._domain = country_data["domain"]
            self._country_code = country_data["country"]
            self._language = country_data["language"]
            await self._refresh_auth_cookies()

    async def auth_check_status(self) -> bool:
        """Check AUTH status."""
        _, raw_resp = await self._session_request(
            method=HTTPMethod.GET,
            url=f"https://alexa.amazon.{self._domain}/api/bootstrap?version=0",
            agent="Browser",
        )
        if raw_resp.status != HTTPStatus.OK:
            _LOGGER.debug(
                "Session not authenticated: reply error %s",
                raw_resp.status,
            )
            return False

        resp_json = await self._response_to_json(raw_resp)
        if not (authentication := resp_json.get("authentication")):
            _LOGGER.debug('Session not authenticated: reply missing "authentication"')
            return False

        authenticated = authentication.get("authenticated")
        _LOGGER.debug("Session authenticated: %s", authenticated)
        return bool(authenticated)

    async def _refresh_data(self, data_type: str) -> tuple[bool, dict]:
        """Refresh data."""
        if not self._login_stored_data:
            _LOGGER.debug("No login data available, cannot refresh")
            return False, {}

        data = {
            "app_name": AMAZON_APP_NAME,
            "app_version": AMAZON_APP_VERSION,
            "di.sdk.version": "6.12.4",
            "source_token": self._login_stored_data["refresh_token"],
            "package_name": AMAZON_APP_BUNDLE_ID,
            "di.hw.version": "iPhone",
            "platform": "iOS",
            "requested_token_type": data_type,
            "source_token_type": "refresh_token",
            "di.os.name": "iOS",
            "di.os.version": AMAZON_CLIENT_OS,
            "current_version": "6.12.4",
            "previous_version": "6.12.4",
            "domain": f"www.amazon.{self._domain}",
        }

        _, raw_resp = await self._session_request(
            HTTPMethod.POST,
            "https://api.amazon.com/auth/token",
            input_data=data,
            json_data=False,
        )
        _LOGGER.debug(
            "Refresh data response %s with payload %s",
            raw_resp.status,
            orjson.dumps(data),
        )

        if raw_resp.status != HTTPStatus.OK:
            _LOGGER.debug("Failed to refresh data")
            return False, {}

        json_response = await self._response_to_json(raw_resp)
        _LOGGER.debug("Refresh data json:\n%s ", json_response)

        if data_type == REFRESH_ACCESS_TOKEN and (
            new_token := json_response.get(REFRESH_ACCESS_TOKEN)
        ):
            self._login_stored_data[REFRESH_ACCESS_TOKEN] = new_token
            self.expires_in = datetime.now(tz=UTC).timestamp() + int(
                json_response.get("expires_in", 0)
            )
            return True, json_response

        if data_type == REFRESH_AUTH_COOKIES:
            return True, json_response

        _LOGGER.debug("Unexpected refresh data response")
        return False, {}
