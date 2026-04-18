"""HTTP2 Support for Amazon devices."""

import asyncio
import contextlib
import re
from email.parser import BytesParser
from email.policy import default
from http import HTTPMethod, HTTPStatus
from typing import Any, cast

import httpx
import orjson
from aiosignal import Signal

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
_MAX_BUFFER_SIZE = 512 * 1024  # 512 KB
_PING_INTERVAL = 280
# How long to wait for the stream to open before the ping loop retries.
_OPEN_TIMEOUT = 30


class AmazonHTTP2Client:
    """Amazon push HTTP2 messages."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
        httpx_client: httpx.AsyncClient,
    ) -> None:
        """Initialize Amazon HTTP2 client class."""
        self._http_wrapper = http_wrapper
        self._session_state_data = session_state_data

        self._http2_client = httpx_client
        self.on_push_event: Signal[str, dict[str, Any]] = Signal(self)

        self._stream_task: asyncio.Task[None] | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._connected_event = asyncio.Event()

    async def start_processing(self) -> None:
        """Start the background stream and ping tasks."""
        if self._stream_task and not self._stream_task.done():
            return

        self._stop_event.clear()
        self._connected_event.clear()
        self._stream_task = asyncio.create_task(
            self._get_avs_directives(), name="avs-stream"
        )
        self._ping_task = asyncio.create_task(self._ping_loop(), name="avs-ping")

    async def stop_processing(self) -> None:
        """Stop all background tasks gracefully."""
        self._stop_event.set()
        self._connected_event.clear()

        for task in (self._stream_task, self._ping_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

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
            self._connected_event.clear()

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
        """Ensure token and device registration are ready."""
        refreshed_token, _ = await self._http_wrapper.refresh_data(REFRESH_ACCESS_TOKEN)

        if not refreshed_token:
            _LOGGER.warning("Failed to refresh access token")
            return False

        if not self._session_state_data.login_stored_data.get(
            DEVICE_CAPABILITIES_REGISTERED, False
        ):
            _LOGGER.debug("Registering device capabilities")
            await self._register_device_capabilities()

        return True

    async def _stream_and_process(self) -> None:
        """Open stream and process incoming directives."""
        _LOGGER.debug("Starting AVS Directives stream")

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
                raise CannotAuthenticate(
                    f"Directives stream returned {response.status_code}"
                )

            boundary = self._parse_boundary(response.headers.get("content-type", ""))
            if boundary is None:
                _LOGGER.warning("Missing multipart boundary")
                return

            # Stream confirmed open — allow the ping loop to start firing.
            self._connected_event.set()

            buffer = bytearray()

            try:
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

                        try:
                            await self._handle_part(part.strip())
                        except AttributeError as exc:
                            _LOGGER.warning(
                                "Error processing multipart section: %s",
                                part.decode("utf-8", errors="replace"),
                                exc_info=exc,
                            )
            finally:
                _LOGGER.debug("AVS Directives stream closed")
                self._connected_event.clear()

    async def _handle_part(self, part: bytes) -> None:
        """Process a single multipart section."""
        if not part:
            with contextlib.suppress(Exception):
                await self._ping()
            return

        try:
            chunk_json = self._extract_json_from_part(part)
        except (ValueError, orjson.JSONDecodeError) as exc:
            _LOGGER.warning(
                "Failed to parse multipart section: %s",
                part.decode("utf-8", errors="replace"),
                exc_info=exc,
            )
            return

        try:
            updates_nodes = chunk_json["directive"]["payload"]["renderingUpdates"]
        except (KeyError, TypeError):
            _LOGGER.warning("Malformed directive payload: %s", chunk_json)
            return

        if not isinstance(updates_nodes, list):
            _LOGGER.warning("Malformed renderingUpdates payload: %s", updates_nodes)
            return

        # All observed messages appear to contain only one update
        # but this is treated as an array to ensure we iterate over all results
        for updates_node in updates_nodes:
            push_event_type = updates_node.get("resourceId", "No resourceId")
            payload = updates_node.get("resourceMetadata", {}).get("payload", {})
            device = payload.get("dopplerId", {}).get("deviceSerialNumber")

            if push_event_type not in AmazonPushMessage._value2member_map_:
                _LOGGER.warning(
                    "Unknown HTTP2 push message from device %s: %s\n\n%s",
                    device,
                    push_event_type,
                    chunk_json,
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
            raise ValueError(f"Unexpected content-type: {msg.get_content_type()!r}")

        if (body := msg.get_payload(decode=True)) is None:
            raise ValueError("No payload")

        parsed = orjson.loads(body)
        return cast("dict[str, Any]", self._string_recursive_parse(parsed))

    def _http2_site(self) -> str:
        """Get HTTP2 site."""
        region = self._session_state_data.login_stored_data["customer_info"][
            "home_region"
        ]
        return HTTP2_SITE.format(region=region)

    async def _ping_loop(self) -> None:
        """Send periodic keepalive pings independent of server-side frames.

        The loop waits for _connected_event before its first ping so it
        never fires while the stream is still being established or while
        a reconnect is in progress.
        """
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._connected_event.wait(), timeout=_OPEN_TIMEOUT
                )
            except TimeoutError:
                continue  # not connected yet — loop back and wait again

            await asyncio.sleep(_PING_INTERVAL)

            if self._stop_event.is_set():
                break
            if not self._connected_event.is_set():
                # Disconnected during the sleep — skip ping, let the stream
                # task reconnect.
                continue

            try:
                await self._ping()
            except CannotAuthenticate:
                _LOGGER.warning("HTTP2: Ping auth failure")
                self._connected_event.clear()
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("HTTP2: Ping error (will retry): %s", exc)

    async def _ping(self) -> None:
        """POST a keepalive to the AVS /ping endpoint."""
        if self._http2_client.is_closed:
            return

        response = await self._http2_client.post(
            f"{self._http2_site()}/ping",
            headers={"Authorization": f"Bearer {self._get_bearer_token()}"},
        )
        _LOGGER.debug("HTTP2: Ping -> %s", response.status_code)

        if response.status_code in (
            HTTPStatus.FORBIDDEN,
            HTTPStatus.PROXY_AUTHENTICATION_REQUIRED,
            HTTPStatus.UNAUTHORIZED,
        ):
            raise CannotAuthenticate(
                f"Ping returned {response.status_code}; check credentials and region"
            )

    def _get_bearer_token(self) -> str:
        """Return the current access token."""
        if not (
            token := self._session_state_data.login_stored_data.get("access_token")
        ):
            _LOGGER.error("No access token available")
            return ""
        return str(token)

    def _parse_boundary(self, content_type: str) -> bytes | None:
        """Extract the boundary delimiter from a Content-Type header value.

        Returns the full delimiter bytes (with '--' prefix) ready for use
        with bytes.find().
        """
        if not (match := _BOUNDARY_RE.search(content_type)):
            return None
        return f"--{match.group(1).strip()}".encode()
