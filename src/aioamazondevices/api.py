"""Support for Amazon devices."""

import base64
import hashlib
import mimetypes
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlencode

import orjson
from aiohttp import ClientResponse, ClientSession
from babel import Locale
from bs4 import BeautifulSoup, Tag
from yarl import URL

from .const import (
    _LOGGER,
    AMAZON_APP_BUNDLE_ID,
    AMAZON_APP_ID,
    AMAZON_APP_NAME,
    AMAZON_APP_VERSION,
    AMAZON_CLIENT_OS,
    AMAZON_DEVICE_SOFTWARE_VERSION,
    AMAZON_DEVICE_TYPE,
    BIN_EXTENSION,
    CSRF_COOKIE,
    DEFAULT_ASSOC_HANDLE,
    DEFAULT_HEADERS,
    DOMAIN_BY_ISO3166_COUNTRY,
    HTML_EXTENSION,
    JSON_EXTENSION,
    NODE_BLUETOOTH,
    NODE_DEVICES,
    NODE_DO_NOT_DISTURB,
    NODE_PREFERENCES,
    SAVE_PATH,
    URI_QUERIES,
)
from .exceptions import CannotAuthenticate, CannotRegisterDevice, WrongMethod


@dataclass
class AmazonDevice:
    """Amazon device class."""

    account_name: str
    capabilities: list[str]
    device_family: str
    device_type: str
    device_owner_customer_id: str
    online: bool
    serial_number: str
    software_version: str
    do_not_disturb: bool
    response_style: str | None
    bluetooth_state: bool


class AmazonEchoApi:
    """Queries Amazon for Echo devices."""

    def __init__(
        self,
        login_country_code: str,
        login_email: str,
        login_password: str,
        login_data: dict[str, Any] | None = None,
        save_raw_data: bool = False,
    ) -> None:
        """Initialize the scanner."""
        # Force country digits as lower case
        country_code = login_country_code.lower()

        locale = DOMAIN_BY_ISO3166_COUNTRY.get(country_code)
        domain = locale["domain"] if locale else country_code

        if locale and (assoc := locale.get("openid.assoc_handle")):
            assoc_handle = assoc
        else:
            assoc_handle = f"{DEFAULT_ASSOC_HANDLE}_{country_code}"
        self._assoc_handle = assoc_handle

        self._login_email = login_email
        self._login_password = login_password
        self._login_country_code = country_code
        self._domain = domain
        self._cookies = self._build_init_cookies()
        self._csrf_cookie: str | None = None
        self._headers = DEFAULT_HEADERS
        self._save_raw_data = save_raw_data
        self._login_stored_data = login_data
        self._serial = self._serial_number()

        self.session: ClientSession

    def _load_website_cookies(self) -> list[SimpleCookie]:
        """Get website cookies, if avaliables."""
        if not self._login_stored_data:
            return []

        return cast("list", self._login_stored_data["website_cookies"])

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

        return {"frc": frc, "map-md": map_md, "amzn-app-id": AMAZON_APP_ID}

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
        form = soup.find("form", {"name": "signIn"}) or soup.find("form")
        if isinstance(form, Tag):
            method = form["method"]
            url = form["action"]
            if isinstance(method, str) and isinstance(url, str):
                return method, url
        raise TypeError("Unable to extract form data from response.")

    def _extract_code_from_url(self, url: URL) -> str:
        """Extract the access token from url query after login."""
        parsed_url = parse_qs(url.query.decode())
        return parsed_url["openid.oa2.authorization_code"][0]

    def _client_session(self) -> None:
        """Create HTTP client session."""
        if not hasattr(self, "session") or self.session.closed:
            _LOGGER.debug("Creating HTTP session (aiohttp)")
            self.session = ClientSession(
                headers=DEFAULT_HEADERS,
                cookies=self._cookies,
            )

    async def _session_request(
        self,
        method: str,
        url: str,
        input_data: dict[str, Any] | None = None,
        json_data: bool = False,
    ) -> tuple[BeautifulSoup, ClientResponse]:
        """Return request response context data."""
        _LOGGER.debug(
            "%s request: %s with payload %s [json=%s]",
            method,
            url,
            input_data,
            json_data,
        )

        headers = DEFAULT_HEADERS
        if self._csrf_cookie and CSRF_COOKIE not in headers:
            csrf = {CSRF_COOKIE: self._csrf_cookie}
            _LOGGER.debug("Adding <%s> to headers", csrf)
            headers.update(csrf)

        if json_data:
            json_header = {"Content-Type": "application/json"}
            _LOGGER.debug("Adding %s to headers", json_header)
            headers.update(json_header)

        resp = await self.session.request(
            method,
            url,
            data=input_data if not json_data else orjson.dumps(input_data),
            cookies=self._load_website_cookies(),
            headers=headers,
            allow_redirects=True,
        )
        content_type: str = resp.headers.get("Content-Type", "")
        _LOGGER.debug(
            "Response %s for url %s with content type: %s",
            resp.status,
            url,
            content_type,
        )

        await self._save_to_file(
            await resp.text(),
            url,
            mimetypes.guess_extension(content_type.split(";")[0]) or ".raw",
        )

        return BeautifulSoup(await resp.read(), "html.parser"), resp

    async def _save_to_file(
        self,
        raw_data: str | dict,
        url: str,
        extension: str = HTML_EXTENSION,
        output_path: str = SAVE_PATH,
    ) -> None:
        """Save response data to disk."""
        if not self._save_raw_data or not raw_data:
            return

        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        if url.startswith("http"):
            url_split = url.split("/")
            base_filename = f"{url_split[3]}-{url_split[4].split('?')[0]}"
        else:
            base_filename = url
        fullpath = Path(output_dir, base_filename + extension)

        if type(raw_data) is dict:
            data = orjson.dumps(raw_data, option=orjson.OPT_INDENT_2).decode("utf-8")
        elif extension in [HTML_EXTENSION, BIN_EXTENSION]:
            data = raw_data
        else:
            data = orjson.dumps(
                orjson.loads(raw_data),
                option=orjson.OPT_INDENT_2,
            ).decode("utf-8")

        i = 2
        while fullpath.exists():
            filename = f"{base_filename}_{i!s}{extension}"
            fullpath = Path(output_dir, filename)
            i += 1

        _LOGGER.warning("Saving data to %s", fullpath)

        with Path.open(fullpath, mode="w", encoding="utf-8") as file:
            file.write(data)
            file.write("\n")

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

        register_url = f"https://api.amazon.{self._domain}/auth/register"
        _, resp = await self._session_request(
            method="POST",
            url=register_url,
            input_data=body,
            json_data=True,
        )
        resp_json = resp.json()

        if resp.status != HTTPStatus.OK:
            _LOGGER.error(
                "Cannot register device for %s: %s",
                self._login_email,
                resp_json["response"]["error"]["message"],
            )
            raise CannotRegisterDevice(resp_json)

        await self._save_to_file(
            resp.text,
            url=register_url,
            extension=JSON_EXTENSION,
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
        await self._save_to_file(login_data, "login_data", JSON_EXTENSION)
        return login_data

    async def login_mode_interactive(self, otp_code: str) -> dict[str, Any]:
        """Login to Amazon interactively via OTP."""
        _LOGGER.debug("Logging-in for %s [otp code %s]", self._login_email, otp_code)
        self._client_session()

        code_verifier = self._create_code_verifier()
        client_id = self._build_client_id()

        _LOGGER.debug("Build oauth URL")
        login_url = self._build_oauth_url(code_verifier, client_id)

        login_soup, _ = await self._session_request(method="GET", url=login_url)
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
            raise CannotAuthenticate

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

        device_login_data = {
            "authorization_code": self._extract_code_from_url(authcode_url),
            "code_verifier": code_verifier,
            "domain": self._domain,
        }

        register_device = await self._register_device(device_login_data)
        self._login_stored_data = register_device

        _LOGGER.info("Register device: %s", register_device)
        return register_device

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
            self._login_email,
        )

        self._client_session()

        return self._login_stored_data

    async def close(self) -> None:
        """Close http client session."""
        if hasattr(self, "session"):
            _LOGGER.debug("Closing HTTP session (aiohttp)")
            await self.session.close()

    async def get_devices_data(
        self,
    ) -> dict[str, AmazonDevice]:
        """Get Amazon devices data."""
        devices: dict[str, Any] = {}
        for key in URI_QUERIES:
            _, raw_resp = await self._session_request(
                method="GET",
                url=f"https://alexa.amazon.{self._domain}{URI_QUERIES[key]}",
            )
            _LOGGER.debug("Response URL: %s", raw_resp.url)
            response_code = raw_resp.status
            _LOGGER.debug("Response code: |%s|", response_code)

            response_data = await raw_resp.text()
            _LOGGER.debug("Response data: |%s|", response_data)

            if not self._csrf_cookie:
                self._csrf_cookie = raw_resp.cookies.get(CSRF_COOKIE).value

            json_data = {} if len(response_data) == 0 else await raw_resp.json()

            _LOGGER.debug("JSON data: |%s|", json_data)

            for data in json_data[key]:
                dev_serial = data.get("serialNumber") or data.get("deviceSerialNumber")
                if previous_data := devices.get(dev_serial):
                    devices[dev_serial] = previous_data | {key: data}
                else:
                    devices[dev_serial] = {key: data}

        final_devices_list: dict[str, AmazonDevice] = {}
        for device in devices.values():
            # Remove stale, orphaned and virtual devices
            if (
                NODE_DEVICES not in device
                or device[NODE_DEVICES].get("deviceType") == AMAZON_DEVICE_TYPE
            ):
                continue

            serial_number: str = device[NODE_DEVICES]["serialNumber"]
            preferences = device.get(NODE_PREFERENCES)
            final_devices_list[serial_number] = AmazonDevice(
                account_name=device[NODE_DEVICES]["accountName"],
                capabilities=device[NODE_DEVICES]["capabilities"],
                device_family=device[NODE_DEVICES]["deviceFamily"],
                device_type=device[NODE_DEVICES]["deviceType"],
                device_owner_customer_id=device[NODE_DEVICES]["deviceOwnerCustomerId"],
                online=device[NODE_DEVICES]["online"],
                serial_number=serial_number,
                software_version=device[NODE_DEVICES]["softwareVersion"],
                do_not_disturb=device[NODE_DO_NOT_DISTURB]["enabled"],
                response_style=preferences["responseStyle"] if preferences else None,
                bluetooth_state=device[NODE_BLUETOOTH]["online"],
            )

        return final_devices_list

    async def auth_check_status(self) -> bool:
        """Check AUTH status."""
        _, raw_resp = await self._session_request(
            method="GET",
            url=f"https://alexa.amazon.{self._domain}/api/bootstrap?version=0",
        )
        if raw_resp.status != HTTPStatus.OK:
            _LOGGER.debug(
                "Session not authenticated: reply error %s",
                raw_resp.status,
            )
            return False

        resp_json = await raw_resp.json()
        if not (authentication := resp_json.get("authentication")):
            _LOGGER.debug('Session not authenticated: reply missing "authentication"')
            return False

        authenticated = authentication.get("authenticated")
        _LOGGER.debug("Session authenticated: %s", authenticated)
        return bool(authenticated)

    async def call_alexa_speak(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> dict[str, Any]:
        """Call Alexa.Speak to send a message."""
        locale_data = Locale.parse(f"und_{self._login_country_code}")
        locale = f"{locale_data.language}-{locale_data.language}"

        if not self._login_stored_data:
            _LOGGER.warning("Trying to send message before login")
            return {}

        sequence = {
            "@type": "com.amazon.alexa.behaviors.model.Sequence",
            "startNode": {
                "@type": "com.amazon.alexa.behaviors.model.SerialNode",
                "nodesToExecute": [
                    {
                        "@type": "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",  # noqa: E501
                        "type": "Alexa.Speak",
                        "operationPayload": {
                            "deviceType": device.device_type,
                            "deviceSerialNumber": device.serial_number,
                            "locale": locale,
                            "customerId": device.device_owner_customer_id,
                            "textToSpeak": message_body,
                            "target": {
                                "customerId": device.device_owner_customer_id,
                                "devices": [
                                    {
                                        "deviceSerialNumber": device.serial_number,
                                        "deviceTypeId": device.device_type,
                                    },
                                ],
                            },
                            "skillId": "amzn1.ask.1p.saysomething",
                        },
                    },
                ],
            },
        }
        node_data = {
            "behaviorId": "PREVIEW",
            "sequenceJson": orjson.dumps(sequence).decode("utf-8"),
            "status": "ENABLED",
        }

        _LOGGER.debug("Preview data payload: %s", node_data)
        await self._session_request(
            method="POST",
            url=f"https://alexa.amazon.{self._domain}/api/behaviors/preview",
            input_data=node_data,
            json_data=True,
        )

        return node_data
