"""Support for Amazon devices."""

import asyncio
import base64
import hashlib
import mimetypes
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from http import HTTPMethod, HTTPStatus
from http.cookies import Morsel
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlencode

import orjson
from aiohttp import (
    ClientConnectorError,
    ClientResponse,
    ClientSession,
)
from bs4 import BeautifulSoup, Tag
from langcodes import Language
from multidict import MultiDictProxy
from yarl import URL

from . import __version__
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
    DEFAULT_AGENT,
    DEFAULT_ASSOC_HANDLE,
    DEFAULT_HEADERS,
    DEFAULT_SITE,
    DEVICE_TO_IGNORE,
    DEVICE_TYPE_TO_MODEL,
    HTML_EXTENSION,
    HTTP_ERROR_199,
    HTTP_ERROR_299,
    JSON_EXTENSION,
    NODE_DEVICES,
    NODE_DO_NOT_DISTURB,
    NODE_IDENTIFIER,
    REFRESH_ACCESS_TOKEN,
    REFRESH_AUTH_COOKIES,
    SAVE_PATH,
    SENSOR_STATE_MOTION_DETECTED,
    URI_NEXUS_GRAPHQL,
    URI_QUERIES,
    URI_SIGNIN,
)
from .exceptions import (
    CannotAuthenticate,
    CannotConnect,
    CannotRegisterDevice,
    CannotRetrieveData,
    WrongMethod,
)
from .utils import obfuscate_email, scrub_fields


@dataclass
class AmazonDeviceSensor:
    """Amazon device sensor class."""

    name: str
    value: str | int | float
    scale: str | None


@dataclass
class AmazonDevice:
    """Amazon device class."""

    account_name: str
    capabilities: list[str]
    device_family: str
    device_type: str
    device_owner_customer_id: str
    device_cluster_members: list[str]
    online: bool
    serial_number: str
    software_version: str
    do_not_disturb: bool
    entity_id: str
    appliance_id: str
    sensors: dict[str, AmazonDeviceSensor]


class AmazonSequenceType(StrEnum):
    """Amazon sequence types."""

    Announcement = "AlexaAnnouncement"
    Speak = "Alexa.Speak"
    Sound = "Alexa.Sound"
    Music = "Alexa.Music.PlaySearchPhrase"
    TextCommand = "Alexa.TextCommand"
    LaunchSkill = "Alexa.Operation.SkillConnections.Launch"


class AmazonMusicSource(StrEnum):
    """Amazon music sources."""

    Radio = "TUNEIN"
    AmazonMusic = "AMAZON_MUSIC"


class AmazonEchoApi:
    """Queries Amazon for Echo devices."""

    def __init__(
        self,
        client_session: ClientSession,
        login_email: str,
        login_password: str,
        login_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the scanner."""
        # Check if there is a previous login, otherwise use default (US)
        site = login_data.get("site", DEFAULT_SITE) if login_data else DEFAULT_SITE
        _LOGGER.debug("Using site: %s", site)
        self._country_specific_data(site)

        self._login_email = login_email
        self._login_password = login_password

        self._cookies = self._build_init_cookies()
        self._save_raw_data = False
        self._login_stored_data = login_data or {}
        self._serial = self._serial_number()
        self._list_for_clusters: dict[str, str] = {}

        self._session = client_session
        self._devices: dict[str, Any] = {}
        self._sensors_available: bool = True

        _LOGGER.debug("Initialize library v%s", __version__)

    @property
    def domain(self) -> str:
        """Return current Amazon domain."""
        return self._domain

    def save_raw_data(self) -> None:
        """Save raw data to disk."""
        self._save_raw_data = True
        _LOGGER.debug("Saving raw data to disk")

    def _country_specific_data(self, domain: str) -> None:
        """Set country specific data."""
        # Force lower case
        domain = domain.replace("https://www.amazon.", "").lower()
        country_code = domain.split(".")[-1] if domain != "com" else "us"

        lang_object = Language.make(territory=country_code.upper())
        lang_maximized = lang_object.maximize()

        self._domain: str = domain
        self._language = f"{lang_maximized.language}-{lang_maximized.region}"

        # Reset CSRF cookie when changing country
        self._csrf_cookie: str | None = None

        _LOGGER.debug(
            "Initialize country <%s>: domain <amazon.%s>, language <%s>",
            country_code.upper(),
            self._domain,
            self._language,
        )

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
            "openid.assoc_handle": DEFAULT_ASSOC_HANDLE,
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "pageId": DEFAULT_ASSOC_HANDLE,
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
            raise TypeError("Unable to find form in login response")

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
        raise TypeError("Unable to extract form data from response")

    def _extract_code_from_url(self, url: URL) -> str:
        """Extract the access token from url query after login."""
        parsed_url: dict[str, list[str]] = {}
        if isinstance(url.query, bytes):
            parsed_url = parse_qs(url.query.decode())
        elif isinstance(url.query, MultiDictProxy):
            for key, value in url.query.items():
                parsed_url[key] = [value]
        else:
            raise TypeError(f"Unable to extract authorization code from url: {url}")
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
        input_data: dict[str, Any] | None = None,
        json_data: bool = False,
        amazon_user_agent: bool = True,
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
        headers.update({"Accept-Language": self._language})
        if not amazon_user_agent:
            _LOGGER.debug("Changing User-Agent to %s", DEFAULT_AGENT)
            headers.update({"User-Agent": DEFAULT_AGENT})
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

        if url.endswith("/auth/token"):
            headers.update(
                {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "x-amzn-identity-auth-domain": "api.amazon.com",
                }
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

        data: str
        if isinstance(raw_data, dict):
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
        _, resp = await self._session_request(
            method=HTTPMethod.POST,
            url=register_url,
            input_data=body,
            json_data=True,
        )
        resp_json = await resp.json()

        if resp.status != HTTPStatus.OK:
            msg = resp_json["response"]["error"]["message"]
            _LOGGER.error(
                "Cannot register device for %s: %s",
                obfuscate_email(self._login_email),
                msg,
            )
            raise CannotRegisterDevice(
                f"{await self._http_phrase_error(resp.status)}: {msg}"
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

    async def _get_devices_state(
        self,
    ) -> dict[str, Any]:
        """Get Device State."""
        query = """
        query getDevicesState ($latencyTolerance: LatencyToleranceValue) {
          listEndpoints(listEndpointsInput: {}) {
            endpoints {
              endpointId: id
              friendlyNameObject { value { text } }
              manufacturer { value { text } }
              model { value { text} }
              serialNumber { value { text } }
              softwareVersion { value { text } }
              creationTime
              enablement
              settings {
                doNotDisturb {
                  id
                  endpointId
                  name
                  toggleValue
                  error {
                    type
                    message
                  }
                }
              }
              displayCategories {
                all { value }
                primary { value }
              }
              alexaEnabledMetadata {
                iconId
                isVisible
                category
                capabilities
              }
              legacyIdentifiers {
                dmsIdentifier {
                  deviceType { value { text } }
                }
                chrsIdentifier { entityId }
              }
              legacyAppliance { applianceId }
              associatedUnits { id }
              connections {
                  type
                  macAddress
                  bleMeshDeviceUuid
              }
              features(latencyToleranceValue: $latencyTolerance) {
                name
                instance
                properties {
                  name
                  type
                  accuracy
                  error { message }
                  __typename
                  ... on Illuminance {
                    illuminanceValue { value }
                    timeOfSample
                    timeOfLastChange
                  }
                  ... on Reachability {
                      reachabilityStatusValue
                      timeOfSample
                      timeOfLastChange
                  }
                  ... on DetectionState {
                      detectionStateValue
                      timeOfSample
                      timeOfLastChange
                  }
                  ... on Volume {
                      value { volValue: value }
                  }
                  ... on TemperatureSensor {
                      name
                      value {
                        value
                        scale
                      }
                      timeOfSample
                      timeOfLastChange
                  }
                }
              }
            }
          }
        }
        """

        payload = {
            "operationName": "getDevicesState",
            "variables": {
                "latencyTolerance": "LOW",
            },
            "query": query,
        }

        _, raw_resp = await self._session_request(
            method=HTTPMethod.POST,
            url=f"https://alexa.amazon.{self._domain}{URI_NEXUS_GRAPHQL}",
            input_data=payload,
            json_data=True,
        )

        devices_state: dict[str, Any] = await raw_resp.json()
        return devices_state

    async def _get_sensors_states(self) -> dict[str, dict[str, AmazonDeviceSensor]]:
        """Retrieve devices sensors states."""
        devices_state = await self._get_devices_state()
        devices_sensors: dict[str, dict[str, AmazonDeviceSensor]] = {}

        endpoints = devices_state["data"]["listEndpoints"]
        for endpoint in endpoints["endpoints"]:
            serial_number = (
                endpoint["serialNumber"]["value"]["text"]
                if endpoint["serialNumber"]
                else None
            )
            if serial_number in self._devices:
                devices_sensors[serial_number] = self._get_device_sensor_state(endpoint)

        return devices_sensors

    def _get_device_sensor_state(
        self, endpoint: dict[str, Any]
    ) -> dict[str, AmazonDeviceSensor]:
        device_sensors: dict[str, AmazonDeviceSensor] = {}
        if endpoint["features"]:
            for feature in endpoint["features"]:
                if feature["name"] == "temperatureSensor":
                    device_sensors["temperature"] = AmazonDeviceSensor(
                        "temperature",
                        feature["properties"][0]["value"]["value"],
                        feature["properties"][0]["value"]["scale"],
                    )
                if feature["name"] == "motionSensor":
                    device_sensors["motion"] = AmazonDeviceSensor(
                        "humanPresenceDetectionState",  # name to match legacy value
                        feature["properties"][0].get("detectionStateValue", "NOT_SET")
                        == SENSOR_STATE_MOTION_DETECTED,
                        None,
                    )
                if feature["name"] == "lightSensor":
                    device_sensors["illuminance"] = AmazonDeviceSensor(
                        "illuminance",
                        feature["properties"][0]["illuminanceValue"]["value"],
                        None,
                    )

        return device_sensors

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
        await self._save_to_file(self._login_stored_data, "login_data", JSON_EXTENSION)

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

        return self._login_stored_data

    async def _get_alexa_domain(self) -> str:
        """Get the Alexa domain."""
        _LOGGER.debug("Retrieve Alexa domain")
        _, raw_resp = await self._session_request(
            method=HTTPMethod.GET,
            url=f"https://alexa.amazon.{self._domain}/api/welcome",
        )
        json_data = await raw_resp.json()
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
            self._country_specific_data(user_domain)
            await self._refresh_auth_cookies()

    async def get_devices_data(
        self,
    ) -> dict[str, AmazonDevice]:
        """Get Amazon devices data."""
        self._devices = {}
        for key in URI_QUERIES:
            _, raw_resp = await self._session_request(
                method=HTTPMethod.GET,
                url=f"https://alexa.amazon.{self._domain}{URI_QUERIES[key]}",
            )

            response_data = await raw_resp.text()
            json_data = {} if len(response_data) == 0 else await raw_resp.json()

            _LOGGER.debug("JSON data: |%s|", scrub_fields(json_data))

            for data in json_data[key]:
                dev_serial = data.get("serialNumber") or data.get("deviceSerialNumber")
                if previous_data := self._devices.get(dev_serial):
                    self._devices[dev_serial] = previous_data | {key: data}
                else:
                    self._devices[dev_serial] = {key: data}

        devices_sensors: dict[
            str, dict[str, AmazonDeviceSensor]
        ] = await self._get_sensors_states()

        final_devices_list: dict[str, AmazonDevice] = {}
        for device in self._devices.values():
            # Remove stale, orphaned and virtual devices
            devices_node = device.get(NODE_DEVICES)
            if not devices_node or (devices_node.get("deviceType") in DEVICE_TO_IGNORE):
                continue

            do_not_disturb_node = device[NODE_DO_NOT_DISTURB]
            identifier_node = device.get(NODE_IDENTIFIER, {})

            serial_number: str = devices_node["serialNumber"]
            # Add sensors
            sensors = devices_sensors.get(serial_number, {})

            final_devices_list[serial_number] = AmazonDevice(
                account_name=devices_node["accountName"],
                capabilities=devices_node["capabilities"],
                device_family=devices_node["deviceFamily"],
                device_type=devices_node["deviceType"],
                device_owner_customer_id=devices_node["deviceOwnerCustomerId"],
                device_cluster_members=(
                    devices_node["clusterMembers"] or [serial_number]
                ),
                online=devices_node["online"],
                serial_number=serial_number,
                software_version=devices_node["softwareVersion"],
                do_not_disturb=do_not_disturb_node["enabled"],
                entity_id=identifier_node.get("entityId"),
                appliance_id=identifier_node.get("applianceId"),
                sensors=sensors,
            )

        self._list_for_clusters.update(
            {
                device.serial_number: device.device_type
                for device in final_devices_list.values()
            }
        )

        return final_devices_list

    async def auth_check_status(self) -> bool:
        """Check AUTH status."""
        _, raw_resp = await self._session_request(
            method=HTTPMethod.GET,
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

    def get_model_details(self, device: AmazonDevice) -> dict[str, str | None] | None:
        """Return model datails."""
        model_details: dict[str, str | None] | None = DEVICE_TYPE_TO_MODEL.get(
            device.device_type
        )
        if not model_details:
            _LOGGER.warning(
                "Unknown device type '%s' for %s: please read https://github.com/chemelli74/aioamazondevices/wiki/Unknown-Device-Types",
                device.device_type,
                device.account_name,
            )

        return model_details

    async def _send_message(
        self,
        device: AmazonDevice,
        message_type: str,
        message_body: str,
        message_source: AmazonMusicSource | None = None,
    ) -> None:
        """Send message to specific device."""
        if not self._login_stored_data:
            _LOGGER.warning("No login data available, cannot send message")
            return

        base_payload = {
            "deviceType": device.device_type,
            "deviceSerialNumber": device.serial_number,
            "locale": self._language,
            "customerId": device.device_owner_customer_id,
        }

        payload: dict[str, Any]
        if message_type == AmazonSequenceType.Speak:
            payload = {
                **base_payload,
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
            }
        elif message_type == AmazonSequenceType.Announcement:
            playback_devices: list[dict[str, str]] = [
                {
                    "deviceSerialNumber": serial,
                    "deviceTypeId": self._list_for_clusters[serial],
                }
                for serial in device.device_cluster_members
                if serial in self._list_for_clusters
            ]

            payload = {
                **base_payload,
                "expireAfter": "PT5S",
                "content": [
                    {
                        "locale": self._language,
                        "display": {
                            "title": "Home Assistant",
                            "body": message_body,
                        },
                        "speak": {
                            "type": "text",
                            "value": message_body,
                        },
                    }
                ],
                "target": {
                    "customerId": device.device_owner_customer_id,
                    "devices": playback_devices,
                },
                "skillId": "amzn1.ask.1p.routines.messaging",
            }
        elif message_type == AmazonSequenceType.Sound:
            payload = {
                **base_payload,
                "soundStringId": message_body,
                "skillId": "amzn1.ask.1p.sound",
            }
        elif message_type == AmazonSequenceType.Music:
            payload = {
                **base_payload,
                "searchPhrase": message_body,
                "sanitizedSearchPhrase": message_body,
                "musicProviderId": message_source,
            }
        elif message_type == AmazonSequenceType.TextCommand:
            payload = {
                **base_payload,
                "skillId": "amzn1.ask.1p.tellalexa",
                "text": message_body,
            }
        elif message_type == AmazonSequenceType.LaunchSkill:
            payload = {
                **base_payload,
                "targetDevice": {
                    "deviceType": device.device_type,
                    "deviceSerialNumber": device.serial_number,
                },
                "connectionRequest": {
                    "uri": "connection://AMAZON.Launch/" + message_body,
                },
            }
        else:
            raise ValueError(f"Message type <{message_type}> is not recognised")

        sequence = {
            "@type": "com.amazon.alexa.behaviors.model.Sequence",
            "startNode": {
                "@type": "com.amazon.alexa.behaviors.model.SerialNode",
                "nodesToExecute": [
                    {
                        "@type": "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",  # noqa: E501
                        "type": message_type,
                        "operationPayload": payload,
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
            method=HTTPMethod.POST,
            url=f"https://alexa.amazon.{self._domain}/api/behaviors/preview",
            input_data=node_data,
            json_data=True,
        )

        return

    async def call_alexa_speak(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> None:
        """Call Alexa.Speak to send a message."""
        return await self._send_message(device, AmazonSequenceType.Speak, message_body)

    async def call_alexa_announcement(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> None:
        """Call AlexaAnnouncement to send a message."""
        return await self._send_message(
            device, AmazonSequenceType.Announcement, message_body
        )

    async def call_alexa_sound(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> None:
        """Call Alexa.Sound to play sound."""
        return await self._send_message(device, AmazonSequenceType.Sound, message_body)

    async def call_alexa_music(
        self,
        device: AmazonDevice,
        message_body: str,
        message_source: AmazonMusicSource,
    ) -> None:
        """Call Alexa.Music.PlaySearchPhrase to play music."""
        return await self._send_message(
            device, AmazonSequenceType.Music, message_body, message_source
        )

    async def call_alexa_text_command(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> None:
        """Call Alexa.Sound to play sound."""
        return await self._send_message(
            device, AmazonSequenceType.TextCommand, message_body
        )

    async def call_alexa_skill(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> None:
        """Call Alexa.LaunchSkill to launch a skill."""
        return await self._send_message(
            device, AmazonSequenceType.LaunchSkill, message_body
        )

    async def set_do_not_disturb(self, device: AmazonDevice, state: bool) -> None:
        """Set do_not_disturb flag."""
        payload = {
            "deviceSerialNumber": device.serial_number,
            "deviceType": device.device_type,
            "enabled": state,
        }
        url = f"https://alexa.amazon.{self._domain}/api/dnd/status"
        await self._session_request(
            method="PUT", url=url, input_data=payload, json_data=True
        )

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

        response = await self._session.post(
            "https://api.amazon.com/auth/token",
            data=data,
        )
        _LOGGER.debug(
            "Refresh data response %s with payload %s",
            response.status,
            orjson.dumps(data),
        )

        if response.status != HTTPStatus.OK:
            _LOGGER.debug("Failed to refresh data")
            return False, {}

        json_response = await response.json()
        _LOGGER.debug("Refresh data json:\n%s ", json_response)

        if data_type == REFRESH_ACCESS_TOKEN and (
            new_token := json_response.get(REFRESH_ACCESS_TOKEN)
        ):
            self._login_stored_data[REFRESH_ACCESS_TOKEN] = new_token
            self.expires_in = datetime.now(tz=UTC).timestamp() + int(
                json_response.get("expires_in")
            )
            return True, json_response

        if data_type == REFRESH_AUTH_COOKIES:
            return True, json_response

        _LOGGER.debug("Unexpected refresh data response")
        return False, {}
