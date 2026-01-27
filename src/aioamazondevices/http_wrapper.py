"""aioamazondevices HTTP wrapper module."""

import asyncio
import base64
import secrets
from collections.abc import Callable, Coroutine
from http import HTTPMethod, HTTPStatus
from http.cookies import Morsel
from typing import Any, cast

import orjson
from aiohttp import (
    ClientConnectorError,
    ClientResponse,
    ClientSession,
    ContentTypeError,
)
from bs4 import BeautifulSoup
from langcodes import Language, standardize_tag
from yarl import URL

from . import __version__
from .const.http import (
    AMAZON_APP_BUNDLE_ID,
    AMAZON_APP_ID,
    AMAZON_APP_NAME,
    AMAZON_APP_VERSION,
    AMAZON_CLIENT_OS,
    AMAZON_DEVICE_SOFTWARE_VERSION,
    ARRAY_WRAPPER,
    CSRF_COOKIE,
    DEFAULT_HEADERS,
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
    CannotRetrieveData,
)
from .utils import _LOGGER, scrub_fields


class AmazonSessionStateData:
    """Amazon session state data class."""

    def __init__(
        self,
        domain: str,
        login_email: str,
        login_password: str,
        login_data: dict[str, Any] | None = None,
    ) -> None:
        """Init state class."""
        self._login_email: str = login_email
        self._login_password: str = login_password
        self._login_stored_data: dict[str, Any] = login_data or {}
        self.country_specific_data(domain)

    @property
    def country_code(self) -> str:
        """Return country code."""
        return self._country_code

    @property
    def domain(self) -> str:
        """Return domain."""
        return self._domain

    @property
    def language(self) -> str:
        """Return language."""
        return self._language

    @property
    def login_email(self) -> str:
        """Return login email."""
        return self._login_email

    @property
    def login_password(self) -> str:
        """Return login password."""
        return self._login_password

    @property
    def login_stored_data(self) -> dict[str, Any]:
        """Return login stored data."""
        return self._login_stored_data

    @login_stored_data.setter
    def login_stored_data(self, data: dict[str, Any]) -> None:
        """Set login stored data."""
        self._login_stored_data = data

    @property
    def account_customer_id(self) -> str | None:
        """Return account customer id."""
        return self._login_stored_data.get("account_customer_id")

    @account_customer_id.setter
    def account_customer_id(self, customer_id: str | None) -> None:
        """Set account customer id."""
        self._login_stored_data["account_customer_id"] = customer_id

    def country_specific_data(self, domain: str) -> None:
        """Set country specific data."""
        # Force lower case
        domain = domain.replace("https://www.amazon.", "").lower()
        country_code = domain.split(".")[-1] if domain != "com" else "us"

        lang_object = Language.make(territory=country_code.upper())
        lang_maximized = lang_object.maximize()

        self._country_code: str = country_code
        self._domain: str = domain
        language = f"{lang_maximized.language}-{lang_maximized.territory}"
        self._language: str = standardize_tag(language)

        _LOGGER.debug(
            "Initialize country <%s>: domain <amazon.%s>, language <%s>",
            country_code.upper(),
            self._domain,
            self._language,
        )


class AmazonHttpWrapper:
    """Amazon HTTP wrapper class."""

    def __init__(
        self,
        client_session: ClientSession,
        session_state_data: AmazonSessionStateData,
        save_to_file: Callable[[str | dict, str, str], Coroutine[Any, Any, None]]
        | None = None,
    ) -> None:
        """Initialize HTTP wrapper."""
        self._session = client_session
        self._session_state_data: AmazonSessionStateData = session_state_data
        self._save_to_file = save_to_file

        self._csrf_cookie: str | None = None
        self._cookies: dict[str, str] = self._build_init_cookies()

    @property
    def cookies(self) -> dict[str, str]:
        """Return the current cookies."""
        return self._cookies

    def _load_website_cookies(self, language: str) -> dict[str, str]:
        """Get website cookies, if available."""
        if not self._session_state_data.login_stored_data:
            return {}

        website_cookies: dict[str, Any] = self._session_state_data.login_stored_data[
            "website_cookies"
        ]
        website_cookies.update(
            {
                "session-token": self._session_state_data.login_stored_data[
                    "store_authentication_cookie"
                ]["cookie"]
            }
        )
        website_cookies.update({"lc-acbit": language})

        return website_cookies

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

    async def set_session_state_data(
        self, session_state_data: AmazonSessionStateData
    ) -> None:
        """Set the current session state data."""
        self._session_state_data = session_state_data

    async def http_phrase_error(self, error: int) -> str:
        """Convert numeric error in human phrase."""
        if error == HTTP_ERROR_199:
            return "Miscellaneous Warning"

        if error == HTTP_ERROR_299:
            return "Miscellaneous Persistent Warning"

        return HTTPStatus(error).phrase

    async def refresh_data(self, data_type: str) -> tuple[bool, dict]:
        """Refresh data."""
        if not self._session_state_data.login_stored_data:
            _LOGGER.debug("No login data available, cannot refresh")
            return False, {}

        data = {
            "app_name": AMAZON_APP_NAME,
            "app_version": AMAZON_APP_VERSION,
            "di.sdk.version": "6.12.4",
            "source_token": self._session_state_data.login_stored_data["refresh_token"],
            "package_name": AMAZON_APP_BUNDLE_ID,
            "di.hw.version": "iPhone",
            "platform": "iOS",
            "requested_token_type": data_type,
            "source_token_type": "refresh_token",
            "di.os.name": "iOS",
            "di.os.version": AMAZON_CLIENT_OS,
            "current_version": "6.12.4",
            "previous_version": "6.12.4",
            "domain": f"www.amazon.{self._session_state_data.domain}",
        }

        _, raw_resp = await self.session_request(
            method=HTTPMethod.POST,
            url="https://api.amazon.com/auth/token",
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

        json_response = await self.response_to_json(raw_resp, data_type)

        if data_type == REFRESH_ACCESS_TOKEN and (
            new_token := json_response.get(REFRESH_ACCESS_TOKEN)
        ):
            self._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN] = new_token
            return True, json_response

        if data_type == REFRESH_AUTH_COOKIES:
            return True, json_response

        _LOGGER.debug("Unexpected refresh data response")
        return False, {}

    async def session_request(
        self,
        method: str,
        url: str,
        input_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        json_data: bool = False,
        extended_headers: dict[str, str] | None = None,
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
        headers.update({"User-Agent": REQUEST_AGENT["Browser"]})
        headers.update({"Accept-Language": self._session_state_data.language})
        headers.update({"x-amzn-client": "github.com/chemelli74/aioamazondevices"})
        headers.update({"x-amzn-build-version": __version__})

        if extended_headers:
            _LOGGER.debug("Adding to headers: %s", extended_headers)
            headers.update(extended_headers)

        if self._csrf_cookie:
            csrf = {CSRF_COOKIE: self._csrf_cookie}
            _LOGGER.debug("Adding to headers: %s", csrf)
            headers.update(csrf)

        if json_data:
            json_header = {"Content-Type": "application/json; charset=utf-8"}
            _LOGGER.debug("Adding to headers: %s", json_header)
            headers.update(json_header)

        _cookies = (
            self._load_website_cookies(self._session_state_data.language)
            if self._session_state_data.login_stored_data
            else self._cookies
        )
        self._session.cookie_jar.update_cookies(
            _cookies, URL(f"amazon.{self._session_state_data.domain}")
        )

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

        if csrf := resp.cookies.get(CSRF_COOKIE, Morsel()).value:
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
                raise CannotAuthenticate(await self.http_phrase_error(resp.status))
            if not await self._ignore_ap_signin_error(resp):
                _LOGGER.debug("Error response content: %s", await resp.text())
                raise CannotRetrieveData(
                    f"Request failed: {await self.http_phrase_error(resp.status)}"
                )

        raw_content = await resp.read()

        if self._save_to_file:
            await self._save_to_file(
                raw_content.decode("utf-8"),
                url,
                content_type,
            )

        return BeautifulSoup(raw_content or "", "html.parser"), resp

    async def response_to_json(
        self, raw_resp: ClientResponse, description: str | None = None
    ) -> dict[str, Any]:
        """Convert response to JSON, if possible."""
        try:
            data = await raw_resp.json(loads=orjson.loads)
            if not data:
                _LOGGER.warning("Empty JSON data received")
                data = {}
            if isinstance(data, list):
                # if anonymous array is returned wrap it inside
                # generated key to convert list to dict
                data = {ARRAY_WRAPPER: data}
            if description:
                _LOGGER.debug("JSON '%s' data: %s", description, scrub_fields(data))
            return cast("dict[str, Any]", data)
        except ContentTypeError as exc:
            raise ValueError("Response not in JSON format") from exc
        except orjson.JSONDecodeError as exc:
            raise ValueError("Response with corrupted JSON format") from exc

    async def clear_cookies(self) -> None:
        """Clear session cookies."""
        self._session.cookie_jar.clear()
        await self.clear_csrf_cookie()

    async def clear_csrf_cookie(self) -> None:
        """Clear CSRF cookie."""
        self._csrf_cookie = None

    async def set_cookies(self, cookies: dict[str, str], domain_url: URL) -> None:
        """Set session cookies."""
        self._session.cookie_jar.update_cookies(cookies, domain_url)
