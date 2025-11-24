"""Support for Amazon login."""

import asyncio
import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPMethod, HTTPStatus
from typing import Any, cast
from urllib.parse import parse_qs, urlencode

import orjson
from bs4 import BeautifulSoup, Tag
from multidict import MultiDictProxy
from yarl import URL

from .const.http import (
    AMAZON_APP_BUNDLE_ID,
    AMAZON_APP_NAME,
    AMAZON_APP_VERSION,
    AMAZON_CLIENT_OS,
    AMAZON_DEVICE_SOFTWARE_VERSION,
    AMAZON_DEVICE_TYPE,
    DEFAULT_SITE,
    REFRESH_ACCESS_TOKEN,
    REFRESH_AUTH_COOKIES,
    URI_DEVICES,
    URI_SIGNIN,
)
from .const.metadata import MAX_CUSTOMER_ACCOUNT_RETRIES
from .exceptions import (
    CannotAuthenticate,
    CannotRegisterDevice,
    CannotRetrieveData,
    WrongMethod,
)
from .http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from .utils import _LOGGER, obfuscate_email, scrub_fields


class AmazonLogin:
    """Amazon login for Echo devices."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Login to Amazon."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper

        self._serial = self._serial_number()

    def _serial_number(self) -> str:
        """Get or calculate device serial number."""
        if not self._session_state_data.login_stored_data:
            # Create a new serial number
            _LOGGER.debug("Cannot find previous login data, creating new serial number")
            return uuid.uuid4().hex.upper()

        _LOGGER.debug("Found previous login data, loading serial number")
        return cast(
            "str",
            self._session_state_data.login_stored_data["device_info"][
                "device_serial_number"
            ],
        )

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
            "language": self._session_state_data.language.replace("-", "_"),
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

    async def _register_device(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Register a dummy Alexa device."""
        authorization_code: str = data["authorization_code"]
        code_verifier: bytes = data["code_verifier"]

        body = {
            "requested_extensions": ["device_info", "customer_info"],
            "cookies": {
                "website_cookies": [],
                "domain": f".amazon.{self._session_state_data.domain}",
            },
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
            "user_context_map": {"frc": self._http_wrapper.cookies["frc"]},
            "requested_token_type": [
                "bearer",
                "mac_dms",
                "website_cookies",
                "store_authentication_cookie",
            ],
        }

        register_url = "https://api.amazon.com/auth/register"
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=register_url,
            input_data=body,
            json_data=True,
        )
        resp_json = await self._http_wrapper.response_to_json(raw_resp)

        if raw_resp.status != HTTPStatus.OK:
            msg = resp_json["response"]["error"]["message"]
            _LOGGER.error(
                "Cannot register device for %s: %s",
                obfuscate_email(self._session_state_data.login_email),
                msg,
            )
            raise CannotRegisterDevice(
                f"{await self._http_wrapper.http_phrase_error(raw_resp.status)}: {msg}"
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

    async def login_mode_interactive(self, otp_code: str) -> dict[str, Any]:
        """Login to Amazon interactively via OTP."""
        _LOGGER.debug(
            "Logging-in for %s [otp code: %s]",
            obfuscate_email(self._session_state_data.login_email),
            bool(otp_code),
        )

        device_login_data = await self._login_mode_interactive_oauth(otp_code)

        login_data = await self._register_device(device_login_data)
        self._session_state_data.login_stored_data = login_data

        await self._domain_refresh_auth_cookies()

        await self.obtain_account_customer_id()

        self._session_state_data.login_stored_data.update(
            {"site": f"https://www.amazon.{self._session_state_data.domain}"}
        )

        return self._session_state_data.login_stored_data

    async def _login_mode_interactive_oauth(
        self, otp_code: str
    ) -> dict[str, str | bytes]:
        """Login interactive via oauth URL."""
        code_verifier = self._create_code_verifier()
        client_id = self._build_client_id()

        _LOGGER.debug("Build oauth URL")
        login_url = self._build_oauth_url(code_verifier, client_id)

        login_soup, _ = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=login_url,
        )
        login_method, login_url = self._get_request_from_soup(login_soup)
        login_inputs = self._get_inputs_from_soup(login_soup)
        login_inputs["email"] = self._session_state_data.login_email
        login_inputs["password"] = self._session_state_data.login_password

        _LOGGER.debug("Register at %s", login_url)
        login_soup, _ = await self._http_wrapper.session_request(
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

        login_soup, login_resp = await self._http_wrapper.session_request(
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
            "domain": self._session_state_data.domain,
        }

    async def login_mode_stored_data(self) -> dict[str, Any]:
        """Login to Amazon using previously stored data."""
        if not self._session_state_data.login_stored_data:
            _LOGGER.debug(
                "Cannot find previous login data,\
                    use login_mode_interactive() method instead",
            )
            raise WrongMethod

        _LOGGER.debug(
            "Logging-in for %s with stored data",
            obfuscate_email(self._session_state_data.login_email),
        )

        await self.obtain_account_customer_id()

        return self._session_state_data.login_stored_data

    async def _get_alexa_domain(self) -> str:
        """Get the Alexa domain."""
        _LOGGER.debug("Retrieve Alexa domain")
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=f"https://alexa.amazon.{self._session_state_data.domain}/api/welcome",
        )
        json_data = await self._http_wrapper.response_to_json(raw_resp)
        return cast(
            "str",
            json_data.get(
                "alexaHostName", f"alexa.amazon.{self._session_state_data.domain}"
            ),
        )

    async def _refresh_auth_cookies(self) -> None:
        """Refresh cookies after domain swap."""
        _, json_token_resp = await self._refresh_data(REFRESH_AUTH_COOKIES)

        # Need to take cookies from response and create them as cookies
        website_cookies = self._session_state_data.login_stored_data[
            "website_cookies"
        ] = {}
        await self._http_wrapper.clear_cookies()

        cookie_json = json_token_resp["response"]["tokens"]["cookies"]
        for cookie_domain in cookie_json:
            for cookie in cookie_json[cookie_domain]:
                new_cookie_value = cookie["Value"].replace(r'"', r"")
                new_cookie = {cookie["Name"]: new_cookie_value}
                await self._http_wrapper.set_cookies(new_cookie, URL(cookie_domain))
                website_cookies.update(new_cookie)
                if cookie["Name"] == "session-token":
                    self._session_state_data.login_stored_data[
                        "store_authentication_cookie"
                    ] = {"cookie": new_cookie_value}

    async def _domain_refresh_auth_cookies(self) -> None:
        """Refresh cookies after domain swap."""
        _LOGGER.debug("Refreshing auth cookies after domain change")

        # Get the new Alexa domain
        user_domain = (await self._get_alexa_domain()).replace("alexa", "https://www")
        if user_domain != DEFAULT_SITE:
            _LOGGER.debug("User domain changed to %s", user_domain)
            self._session_state_data.country_specific_data(user_domain)
            await self._http_wrapper.clear_csrf_cookie()
            await self._refresh_auth_cookies()

    async def _refresh_data(self, data_type: str) -> tuple[bool, dict]:
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

        _, raw_resp = await self._http_wrapper.session_request(
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

        json_response = await self._http_wrapper.response_to_json(raw_resp, data_type)

        if data_type == REFRESH_ACCESS_TOKEN and (
            new_token := json_response.get(REFRESH_ACCESS_TOKEN)
        ):
            self._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN] = new_token
            return True, json_response

        if data_type == REFRESH_AUTH_COOKIES:
            return True, json_response

        _LOGGER.debug("Unexpected refresh data response")
        return False, {}

    async def obtain_account_customer_id(self) -> None:
        """Find account customer id."""
        for retry_count in range(MAX_CUSTOMER_ACCOUNT_RETRIES):
            if not self._session_state_data.account_customer_id:
                await asyncio.sleep(2)  # allow time for device to be registered

            _LOGGER.debug(
                "Lookup customer account ID (attempt %d/%d)",
                retry_count + 1,
                MAX_CUSTOMER_ACCOUNT_RETRIES,
            )
            _, raw_resp = await self._http_wrapper.session_request(
                method=HTTPMethod.GET,
                url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_DEVICES}",
            )

            json_data = await self._http_wrapper.response_to_json(raw_resp, "devices")

            for device in json_data.get("devices", []):
                dev_serial = device.get("serialNumber")
                if not dev_serial:
                    _LOGGER.warning(
                        "Skipping device without serial number: %s",
                        device["accountName"],
                    )
                    continue
                if device["deviceType"] != AMAZON_DEVICE_TYPE:
                    continue

                this_device_serial = self._session_state_data.login_stored_data[
                    "device_info"
                ]["device_serial_number"]

                for subdevice in device["appDeviceList"]:
                    if subdevice["serialNumber"] == this_device_serial:
                        account_owner_customer_id = device["deviceOwnerCustomerId"]
                        _LOGGER.debug(
                            "Setting account owner: %s",
                            account_owner_customer_id,
                        )
                        self._session_state_data.account_customer_id = (
                            account_owner_customer_id
                        )
                        return
        if not self._session_state_data.account_customer_id:
            raise CannotRetrieveData("Cannot find account owner customer ID")
