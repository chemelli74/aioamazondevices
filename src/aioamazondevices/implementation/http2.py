"""HTTP2 Support for Amazon devices."""

import asyncio
import contextlib
import re
from email.parser import BytesParser
from email.policy import default
from http import HTTPMethod, HTTPStatus
from ssl import SSLContext, create_default_context
from typing import Any, cast

import httpx
import orjson
from aiosignal import Signal
from orjson import JSONDecodeError

from aioamazondevices.capabilities import (
    DEVICE_CAPABILITIES,
    DEVICE_CAPABILITIES_REGISTERED,
)
from aioamazondevices.const.http import (
    HTTP2_DIRECTIVES_VERSION,
    HTTP2_RECONNECT_DELAY,
    HTTP2_SITE,
    REFRESH_ACCESS_TOKEN,
    URI_CAPABILITIES,
)
from aioamazondevices.exceptions import CannotAuthenticate, CannotRegisterDevice
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonPushMessage
from aioamazondevices.utils import _LOGGER

_BOUNDARY_RE = re.compile(r'boundary="?([^";,]+)"?', re.IGNORECASE)
_MAX_BUFFER_SIZE = 512 * 1024  # 512KB


class AmazonHTTP2Client:
    """Amazon push HTTP2 messages."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize Amazon HTTP2 client class."""
        self._http_wrapper = http_wrapper
        self._session_state_data = session_state_data

        self._http2_client: httpx.AsyncClient | None = None
        self.on_push_event: Signal[str, dict[str, Any]] = Signal(self)

        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._ssl_context: SSLContext | None = None

    async def start_thread(self) -> None:
        """Start the background task."""
        if self._task and not self._task.done():
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._get_avs_directives())

    async def stop_thread(self) -> None:
        """Stop the background task gracefully."""
        self._stop_event.set()

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        if self._http2_client and not self._http2_client.is_closed:
            await self._http2_client.aclose()

    async def _register_device_capabilities(self) -> None:
        """Register device capabilities."""
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.PUT,
            url=f"https://api.amazonalexa.com/{URI_CAPABILITIES}",
            input_data=DEVICE_CAPABILITIES,
            json_data=True,
            extended_headers={"Authorization": f"Bearer {self._get_bearer_token()}"},
        )

        if raw_resp.status != HTTPStatus.NO_CONTENT:
            raise CannotRegisterDevice(
                f"Register capabilities returned {raw_resp.status} (expected 204)"
            )

        self._session_state_data.login_stored_data[DEVICE_CAPABILITIES_REGISTERED] = (
            True
        )
        _LOGGER.debug("Device capabilities registered successfully")

    async def _get_avs_directives(self) -> None:
        """Maintain AVS directive stream loop."""
        while not self._stop_event.is_set():
            if not await self._ensure_ready():
                await asyncio.sleep(HTTP2_RECONNECT_DELAY)
                continue

            try:
                await self._stream_and_process()
            except httpx.RemoteProtocolError as exc:
                _LOGGER.debug("HTTP2 disconnection detected: %s", exc)
            except httpx.HTTPError as exc:
                _LOGGER.warning("HTTP2 error detected: %s", exc)

            if not self._stop_event.is_set():
                _LOGGER.debug("Reconnecting in %s seconds", HTTP2_RECONNECT_DELAY)
                await asyncio.sleep(HTTP2_RECONNECT_DELAY)

    async def _ensure_ready(self) -> bool:
        """Ensure token, device registration, and HTTP2 client are ready."""
        refreshed_token, _ = await self._http_wrapper.refresh_data(REFRESH_ACCESS_TOKEN)

        if not refreshed_token:
            _LOGGER.warning("Failed to refresh access token")
            return False

        if not self._session_state_data.login_stored_data.get(
            DEVICE_CAPABILITIES_REGISTERED, False
        ):
            _LOGGER.debug("Registering device capabilities")
            await self._register_device_capabilities()

        await self._http2_init_client()
        return True

    async def _stream_and_process(self) -> None:
        """Open stream and process incoming directives."""
        _LOGGER.debug("Starting AVS Directives stream")

        if not self._http2_client:
            _LOGGER.error("HTTP2 client not initialized, cannot stream directives")
            return

        async with self._http2_client.stream(
            "GET",
            f"{self._http2_site()}/v{HTTP2_DIRECTIVES_VERSION}/directives",
            headers={
                "Authorization": f"Bearer {self._get_bearer_token()}",
                "Accept": "multipart/related",
                "Accept-Encoding": "gzip",
            },
        ) as response:
            _LOGGER.debug(
                "AVS Directives response status: %s [%s]",
                response.status_code,
                response.http_version,
            )

            if response.status_code in (
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
            ):
                raise CannotAuthenticate

            boundary = self._parse_boundary(response.headers.get("content-type", ""))
            if boundary is None:
                _LOGGER.warning("Missing multipart boundary")
                return

            buffer = bytearray()

            async for chunk in response.aiter_bytes():
                if self._stop_event.is_set():
                    break

                buffer.extend(chunk)

                if len(buffer) > _MAX_BUFFER_SIZE:
                    _LOGGER.error("Buffer exceeded maximum size, forcing reconnect")
                    return

                while True:
                    idx = buffer.find(boundary)
                    if idx == -1:
                        break

                    part = buffer[:idx]
                    del buffer[: idx + len(boundary)]

                    await self._handle_part(part.strip())

        _LOGGER.debug("AVS Directives stream closed")

    async def _handle_part(self, part: bytes) -> None:
        """Process a single multipart section."""
        if not part:
            await self._ping()
            return

        try:
            chunk_json = self._extract_json_from_part(part)
        except (ValueError, JSONDecodeError) as exc:
            _LOGGER.warning("Failed to parse multipart section: %s", part, exc_info=exc)
            return

        try:
            updates_nodes = chunk_json["directive"]["payload"]["renderingUpdates"]
        except (KeyError, IndexError):
            _LOGGER.warning("Malformed directive payload: %s", chunk_json)
            return

        # All observed messages appear to contain only one update
        # but this is treated as an array to ensure we iterate over all results
        for updates_node in updates_nodes:
            push_event_type = updates_node.get("resourceId", "No resourceId")
            payload = updates_node.get("resourceMetadata", {}).get("payload", {})
            device = payload.get("dopplerId", {}).get("deviceSerialNumber")

            if push_event_type not in AmazonPushMessage._value2member_map_:
                _LOGGER.warning(
                    "Unknown HTTP2 push message from device %s: %s",
                    device,
                    push_event_type,
                )
                continue

            # Skip duplicate NotificationChange pushes
            if (
                push_event_type == AmazonPushMessage.NotificationChange.value
                and payload.get("notificationVersion", 2) % 2 == 0
            ):
                continue

            _LOGGER.debug(
                "Detected push event type <%s> on device <%s>",
                push_event_type,
                device,
            )

            await self.on_push_event.send(push_event_type, payload)

    def _string_recursive_parse(
        self, obj: dict[str, Any] | str | list[Any]
    ) -> dict[str, Any] | list[Any] | str:
        """Recursively parse strings inside dicts/lists if they are valid JSON."""
        if isinstance(obj, dict):
            return {k: self._string_recursive_parse(v) for k, v in obj.items()}

        if isinstance(obj, list):
            return [self._string_recursive_parse(i) for i in obj]

        if isinstance(obj, str) and obj.startswith(("{", "[")):
            try:
                return self._string_recursive_parse(orjson.loads(obj))
            except orjson.JSONDecodeError:
                return obj

        return obj

    def _extract_json_from_part(self, part: bytes) -> dict[str, Any]:
        """Extract JSON using MIME parser."""
        msg = BytesParser(policy=default).parsebytes(part + b"\r\n")

        if msg.get_content_type() != "application/json":
            raise ValueError("Unexpected content-type")

        if (body := msg.get_payload(decode=True)) is None:
            raise ValueError("No payload")

        parsed = orjson.loads(body)
        return cast("dict[str, Any]", self._string_recursive_parse(parsed))

    async def _http2_init_client(self) -> None:
        """Create HTTP2 client session."""
        if self._http2_client and not self._http2_client.is_closed:
            await self._http2_client.aclose()

        if self._ssl_context is None:
            self._ssl_context = await asyncio.to_thread(create_default_context)

        self._http2_client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(None),
            verify=self._ssl_context,
        )
        _LOGGER.debug("Initialized HTTP2 client")

    def _http2_site(self) -> str:
        """Get HTTP2 site."""
        region = self._session_state_data.login_stored_data["customer_info"][
            "home_region"
        ]
        return HTTP2_SITE.format(region=region)

    async def _ping(self) -> None:
        """Ping."""
        if not self._http2_client:
            _LOGGER.error("HTTP2 client not initialized, cannot ping")
            return

        response = await self._http2_client.post(
            f"{self._http2_site()}/ping",
            headers={
                "Authorization": f"Bearer {self._get_bearer_token()}",
            },
        )
        _LOGGER.debug(
            "Received response: %s:%s",
            response.status_code,
            response.text,
        )
        if response.status_code in (
            HTTPStatus.FORBIDDEN,
            HTTPStatus.PROXY_AUTHENTICATION_REQUIRED,
            HTTPStatus.UNAUTHORIZED,
        ):
            raise CannotAuthenticate(
                "Detected ping 403, please check your credentials and region"
            )

    def _get_bearer_token(self) -> str:
        """Get current bearer token."""
        if not (
            token := self._session_state_data.login_stored_data.get("access_token")
        ):
            _LOGGER.error("No access token available, cannot get bearer token")
            return ""
        return str(token)

    def _parse_boundary(self, content_type: str) -> bytes | None:
        if not (match := _BOUNDARY_RE.search(content_type)):
            return None
        return f"--{match.group(1).strip()}".encode()
