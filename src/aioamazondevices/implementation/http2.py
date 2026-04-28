"""HTTP2 Support for Amazon devices."""

import asyncio
from email.message import EmailMessage
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
from aioamazondevices.exceptions import (
    CannotAuthenticate,
    CannotConnect,
    CannotRegisterDevice,
    CannotRetrieveData,
)
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonPushMessage
from aioamazondevices.utils import _LOGGER

_MAX_BUFFER_SIZE = 512 * 1024  # 512 KB
_PING_INTERVAL = 280
# How long to wait for the stream to open before the ping loop retries.
_OPEN_TIMEOUT = 30


class AvsDirectiveStreamParser:
    """Parse the raw bytes in AVS Directives into chunks."""

    def __init__(self, boundary: bytes) -> None:
        """Create AVS Directive stream parser."""
        self._boundary = boundary
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        """Feed received input into buffer and parse."""
        self._buffer.extend(chunk)
        if len(self._buffer) > _MAX_BUFFER_SIZE:
            raise BufferError("buffer exceeded")

        parts: list[bytes] = []
        while True:
            idx = self._buffer.find(self._boundary)
            if idx == -1:
                break
            part = bytes(self._buffer[:idx]).strip()
            del self._buffer[: idx + len(self._boundary)]
            parts.append(part)
        return parts


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
        self.on_http_error: Signal[BaseException] = Signal(self)

        self._stream_task: asyncio.Task[None] | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._stop_event = asyncio.Event()
        self._connected_event = asyncio.Event()
        self._process_lock = asyncio.Lock()

    async def start_processing(self) -> None:
        """Start the background stream and ping tasks."""
        async with self._process_lock:
            if (
                self._stream_task
                and not self._stream_task.done()
                and self._ping_task
                and not self._ping_task.done()
            ):
                _LOGGER.debug(
                    "Trying to start http2 processing but both tasks already running"
                )
                return

            # at most one task is running so cancel any running tasks
            await self._cancel_tasks()

            self._stop_event.clear()
            self._connected_event.clear()
            self._stream_task = asyncio.create_task(
                self._get_avs_directives(), name="avs-stream"
            )
            self._stream_task.add_done_callback(self._on_task_done)
            self._ping_task = asyncio.create_task(self._ping_loop(), name="avs-ping")
            self._ping_task.add_done_callback(self._on_task_done)

    async def stop_processing(self) -> None:
        """Stop all background tasks gracefully."""
        async with self._process_lock:
            self._stop_event.set()
            self._connected_event.clear()
            await self._cancel_tasks()

    async def _on_task_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        if (exc := task.exception()) and self.on_http_error.frozen():
            # Needs to be something other than ValueError
            exc_details = ValueError(f"Task {task.get_name()} Failed")
            exc_details.__cause__ = exc
            signal_task = asyncio.create_task(self.on_http_error.send(exc_details))
            self._background_tasks.add(signal_task)
            signal_task.add_done_callback(self._background_tasks.discard)

    async def _cancel_tasks(self) -> None:
        for task in (self._stream_task, self._ping_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    if (
                        current_task := asyncio.current_task()
                    ) and current_task.cancelling():
                        raise

    async def _register_device_capabilities(self) -> None:
        """Register device capabilities."""
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.PUT,
            url=f"https://api.amazonalexa.com{URI_CAPABILITIES}",
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

            try:
                if not (
                    await self._refresh_token()
                    and await self._check_device_capabilities_registered()
                ):
                    await asyncio.sleep(HTTP2_RECONNECT_DELAY)
                    continue

                await self._stream_and_process()
            except httpx.RemoteProtocolError as exc:
                _LOGGER.debug("HTTP2 disconnection detected: %s", exc)
            except httpx.HTTPError as exc:
                _LOGGER.warning("HTTP2 error detected: %s", exc)
            except Exception:
                _LOGGER.exception("Unexpected error getting AVS directive")
                raise

            if not self._stop_event.is_set():
                _LOGGER.debug("Reconnecting in %s seconds", HTTP2_RECONNECT_DELAY)
                await asyncio.sleep(HTTP2_RECONNECT_DELAY)

    async def _refresh_token(self) -> bool:
        """Refresh the access token."""
        try:
            refreshed_token, _ = await self._http_wrapper.refresh_data(
                REFRESH_ACCESS_TOKEN
            )
            if not refreshed_token:
                _LOGGER.warning("Failed to refresh access token")
                return False
        except (CannotConnect, CannotRetrieveData) as exc:
            _LOGGER.warning("Failed to refresh access token: %s", exc)
            return False
        return True

    async def _check_device_capabilities_registered(self) -> bool:
        """Ensure token and device registration are ready."""
        if not self._session_state_data.login_stored_data.get(
            DEVICE_CAPABILITIES_REGISTERED, False
        ):
            _LOGGER.debug("Registering device capabilities")
            try:
                await self._register_device_capabilities()
            except (CannotConnect, CannotRetrieveData) as exc:
                _LOGGER.warning("Failed to register device capabilities: %s", exc)
                return False

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

            boundary = AmazonHTTP2Client._parse_boundary(
                response.headers.get("content-type", "")
            )
            if boundary is None:
                _LOGGER.warning("Missing multipart boundary")
                return

            # Stream confirmed open — allow the ping loop to start firing.
            self._connected_event.set()

            avs_stream_parser = AvsDirectiveStreamParser(boundary)

            try:
                async for chunk in response.aiter_bytes():
                    if self._stop_event.is_set():
                        break

                    for part in avs_stream_parser.feed(chunk):
                        await self._handle_part(part)
            except BufferError:
                _LOGGER.error("Buffer exceeded maximum size, forcing reconnect")
                return
            finally:
                _LOGGER.debug("AVS Directives stream closed")
                self._connected_event.clear()

    async def _handle_part(self, part: bytes) -> None:
        """Process a single multipart section."""
        if not part:
            _LOGGER.debug("Handled empty part.")
            return

        chunk_json = AmazonHTTP2Client.extract_json_from_part(part)
        if chunk_json is None:
            return

        rendering_updates = AmazonHTTP2Client.extract_rendering_updates(chunk_json)
        if rendering_updates is None:
            return

        # All observed messages only contain one update but it is presented
        # as an array so iterate over all results in case that ever changes.
        for rendering_update in rendering_updates:
            result = AmazonHTTP2Client.process_rendering_update(rendering_update)
            if result is None:
                continue
            push_event_type, payload = result
            await self.on_push_event.send(push_event_type, payload)

    @staticmethod
    def process_rendering_update(  # noqa: PLR0911
        rendering_update: object,
    ) -> tuple[str, dict[str, Any]] | None:
        """Process a single rendering update node."""
        if not isinstance(rendering_update, dict):
            _LOGGER.warning("Malformed rendering update node: %s", rendering_update)
            return None

        push_event_type = rendering_update.get("resourceId")
        if not push_event_type:
            _LOGGER.warning("Missing resourceId in update node: %s", rendering_update)
            return None

        resource_metadata = rendering_update.get("resourceMetadata")
        if not isinstance(resource_metadata, dict):
            _LOGGER.warning("Malformed resourceMetadata: %s", rendering_update)
            return None

        payload = resource_metadata.get("payload")
        if not isinstance(payload, dict):
            _LOGGER.warning("Malformed push payload: %s", rendering_update)
            return None

        doppler_id = payload.get("dopplerId") or {}
        device_serial = doppler_id.get("deviceSerialNumber")

        if not AmazonHTTP2Client.is_known_event_type(push_event_type):
            _LOGGER.warning(
                "Unknown HTTP2 push message from device %s: %s\n\n%s",
                device_serial,
                push_event_type,
                rendering_update,
            )
            return None

        if AmazonHTTP2Client.is_duplicate_notification(push_event_type, payload):
            return None

        _LOGGER.debug(
            "Detected push event type <%s> on device <%s>",
            push_event_type,
            device_serial,
        )
        return push_event_type, payload

    @staticmethod
    def extract_rendering_updates(
        chunk_json: dict[str, Any],
    ) -> list[dict[str, Any]] | None:
        """Extract renderingUpdates list from directive payload."""
        try:
            updates_nodes = chunk_json["directive"]["payload"]["renderingUpdates"]
        except (KeyError, TypeError):
            _LOGGER.warning("Malformed directive payload: %s", chunk_json)
            return None

        if not isinstance(updates_nodes, list):
            _LOGGER.warning("Malformed renderingUpdates payload: %s", updates_nodes)
            return None

        return updates_nodes

    @staticmethod
    def is_known_event_type(push_event_type: str) -> bool:
        """Check if the push event type is known."""
        return push_event_type in AmazonPushMessage._value2member_map_

    @staticmethod
    def is_duplicate_notification(
        push_event_type: str, payload: dict[str, Any]
    ) -> bool:
        """Filter duplicate NotificationChange events.

        Observed behavior: even notificationVersion values are duplicates.
        """
        notification_version = payload.get("notificationVersion", 2)
        if not isinstance(notification_version, int):
            _LOGGER.warning(
                f"Unexpected notification_version of {type(notification_version)}"
            )
            return False
        return (
            push_event_type == AmazonPushMessage.NotificationChange.value
            and notification_version % 2 == 0
        )

    @staticmethod
    def string_recursive_parse(
        obj: dict[str, Any] | str | list[Any],
    ) -> dict[str, Any] | list[Any] | str:
        """Recursively parse strings inside dicts/lists if they are valid JSON."""
        if isinstance(obj, dict):
            return {
                k: AmazonHTTP2Client.string_recursive_parse(v) for k, v in obj.items()
            }

        if isinstance(obj, list):
            return [AmazonHTTP2Client.string_recursive_parse(i) for i in obj]

        if isinstance(obj, str) and obj.startswith(("{", "[")):
            try:
                return AmazonHTTP2Client.string_recursive_parse(orjson.loads(obj))
            except orjson.JSONDecodeError:
                return obj

        return obj

    @staticmethod
    def extract_json_from_part(part: bytes) -> dict[str, Any] | None:
        """Extract JSON using MIME parser."""

        def _validate_content_type(content_type: str) -> None:
            if content_type != "application/json":
                raise ValueError(f"Unexpected content-type: {content_type!r}")

        def _get_payload(msg: EmailMessage) -> bytes:
            payload = msg.get_payload(decode=True)
            if payload is None:
                raise ValueError("No payload")
            if not isinstance(payload, bytes):
                raise TypeError(f"Expected bytes payload, got {type(payload)!r}")
            return payload

        try:
            msg = BytesParser(policy=default).parsebytes(part + b"\r\n")
            _validate_content_type(msg.get_content_type())
            body = _get_payload(msg)
            parsed = orjson.loads(body)
            return cast(
                "dict[str, Any]", AmazonHTTP2Client.string_recursive_parse(parsed)
            )
        except (TypeError, ValueError, orjson.JSONDecodeError) as exc:
            _LOGGER.warning(
                "Failed to parse multipart section: %s",
                part.decode("utf-8", errors="replace"),
                exc_info=exc,
            )
            return None

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
            token := self._session_state_data.login_stored_data.get(
                REFRESH_ACCESS_TOKEN
            )
        ):
            _LOGGER.error("No access token available")
            raise CannotAuthenticate("No access token available")
        return str(token)

    @staticmethod
    def _parse_boundary(content_type: str) -> bytes | None:
        """Extract the boundary delimiter from a Content-Type header value.

        Returns the full delimiter bytes (with '--' prefix) ready for use
        with bytes.find().
        """
        msg = EmailMessage()
        msg["Content-Type"] = content_type
        if not (boundary := msg.get_boundary()):
            return None
        return f"--{boundary}".encode()
