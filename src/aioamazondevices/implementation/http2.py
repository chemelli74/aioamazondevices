"""HTTP2 Support for Amazon devices."""

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from http import HTTPStatus
from typing import Any

import httpx
import orjson
from aiosignal import Signal

from aioamazondevices.const.http import (
    HTTP2_DIRECTIVES_VERSION,
    HTTP2_RECONNECT_DELAY,
    HTTP2_SITE,
    REFRESH_ACCESS_TOKEN,
)
from aioamazondevices.exceptions import (
    CannotAuthenticate,
    CannotConnect,
    CannotRetrieveData,
    UpdatedAVSSite,
)
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonPushMessage
from aioamazondevices.utils import (
    _LOGGER,
    http2_extract_json_from_part,
    http2_parse_boundary_delimiter,
)

_MAX_BUFFER_SIZE = 512 * 1024  # 512 KB
_PING_INTERVAL = 280
# How long to wait for the stream to open before the ping loop retries.
_OPEN_TIMEOUT = 30


def _extract_rendering_updates(
    chunk_json: dict[str, Any],
) -> list[object] | None:
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


def _is_notification_change_duplicate(payload: dict[str, Any]) -> bool:
    """Filter duplicate NotificationChange events.

    Observed behavior: even notificationVersion values are duplicates.
    """
    # Ignore AmazonPushMessage.NotificationChange duplicates
    # where notificationVersion is even
    notification_version = payload.get("notificationVersion", 1)
    if not isinstance(notification_version, int):
        _LOGGER.warning(
            "Unexpected type of notification_version: %s", type(notification_version)
        )
        return False

    is_duplicate = notification_version % 2 == 0
    _LOGGER.debug(
        "Checking for duplicate NotificationChange: version=%s, is_duplicate=%s",
        notification_version,
        is_duplicate,
    )
    return is_duplicate


def _is_known_event_type(push_event_type: str) -> bool:
    """Check if the push event type is known."""
    return push_event_type in AmazonPushMessage._value2member_map_


def _process_rendering_update(  # noqa: PLR0911
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

    if not _is_known_event_type(push_event_type):
        _LOGGER.warning(
            "Unknown HTTP2 push message from device %s: %s\n\n%s",
            device_serial,
            push_event_type,
            rendering_update,
        )
        return None

    if (
        push_event_type == AmazonPushMessage.NotificationChange.value
        and _is_notification_change_duplicate(payload)
    ):
        return None

    _LOGGER.debug(
        "Detected push event type <%s> on device <%s>",
        push_event_type,
        device_serial,
    )
    return push_event_type, payload


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
        on_reauth_required: Callable[[], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        """Initialize Amazon HTTP2 client class."""
        self._http_wrapper = http_wrapper
        self._session_state_data = session_state_data

        self._http2_client = httpx_client

        region = self._session_state_data.login_stored_data["customer_info"][
            "home_region"
        ]
        self._avs_directive_site: str = HTTP2_SITE.format(region=region)

        self.on_push_event: Signal[str, dict[str, Any]] = Signal(self)

        self._on_reauth_required = on_reauth_required

        self._run_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._connected_event = asyncio.Event()
        self._process_lock = asyncio.Lock()

        self._reconnect_attempt: int = 0

    async def start_processing(self) -> asyncio.Task[None]:
        """Start background processing. Returns the task to the caller."""
        async with self._process_lock:
            if self._run_task and not self._run_task.done():
                _LOGGER.debug(
                    "Trying to start http2 processing but task already running"
                )
                return self._run_task

            self._stop_event.clear()
            self._connected_event.clear()
            self._run_task = asyncio.create_task(self._run_tasks(), name="amazon-http2")
            return self._run_task

    async def stop_processing(self) -> None:
        """Stop all background tasks gracefully."""
        async with self._process_lock:
            self._stop_event.set()
            self._connected_event.clear()
            if self._run_task and not self._run_task.done():
                self._run_task.cancel()
                try:
                    await self._run_task
                except asyncio.CancelledError:
                    if (t := asyncio.current_task()) and t.cancelling():
                        raise
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Error while stopping http2 processing")
                finally:
                    self._run_task = None

    async def _run_tasks(self) -> None:
        """Run stream and ping tasks until stopped or an unhandled exception occurs."""
        self._reconnect_attempt = 0
        while not self._stop_event.is_set():
            # exponential backoff with a max of 10 minutes between reconnect attempts
            # the backoff resets after a successful ping
            delay = min(HTTP2_RECONNECT_DELAY * (2**self._reconnect_attempt), 600)

            reauth_required = False
            restart_required = False
            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._get_avs_directives(), name="avs-stream")
                    tg.create_task(self._ping_loop(), name="avs-ping")

            except* CannotAuthenticate as auth_exc_group:
                for auth_exc in auth_exc_group.exceptions:
                    _LOGGER.warning(
                        "HTTP2 auth failure",
                        exc_info=(type(auth_exc), auth_exc, auth_exc.__traceback__),
                    )
                reauth_required = True

            except* httpx.RemoteProtocolError as disc_exc_group:
                for disc_exc in disc_exc_group.exceptions:
                    _LOGGER.debug(
                        "HTTP2 disconnection detected",
                        exc_info=(type(disc_exc), disc_exc, disc_exc.__traceback__),
                    )
                restart_required = True

            except* httpx.ReadError as read_exc_group:
                for read_exc in read_exc_group.exceptions:
                    task = asyncio.current_task()
                    if self._stop_event.is_set() or (task and task.cancelling()):
                        _LOGGER.debug("Stream interrupted during shutdown (expected)")
                    else:
                        _LOGGER.debug(
                            "HTTP2 stream read error, reconnecting in %s seconds",
                            delay,
                            exc_info=(type(read_exc), read_exc, read_exc.__traceback__),
                        )
                        restart_required = True

            except* httpx.HTTPError as http_exc_group:
                for http_exc in http_exc_group.exceptions:
                    _LOGGER.warning(
                        "HTTP2 error detected, reconnecting in %s seconds",
                        delay,
                        exc_info=(type(http_exc), http_exc, http_exc.__traceback__),
                    )
                restart_required = True

            except* Exception as exc_group:  # noqa: BLE001
                for exc in exc_group.exceptions:
                    _LOGGER.warning(
                        "HTTP2 failure, reconnecting in %s seconds",
                        delay,
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
                restart_required = True

            if reauth_required:
                if self._on_reauth_required:
                    await self._on_reauth_required()
                break
            if restart_required:
                await asyncio.sleep(delay)
                self._reconnect_attempt += 1

    async def _check_avs_site(self) -> None:
        """Check the AVS site by sending a test event.

        "home_region" from the customer info is not always correct
        so if we get a response from the wrong site attempt to extract
        the correct site from the response and update it for future requests.
        """
        url = f"{self._avs_directive_site}/v{HTTP2_DIRECTIVES_VERSION}/events"

        metadata = {
            "context": [],
            "event": {
                "header": {
                    "namespace": "System",
                    "name": "SynchronizeState",
                    "messageId": str(uuid.uuid4()),
                },
                "payload": {},
            },
        }

        files = {
            "metadata": (None, orjson.dumps(metadata), "application/json"),
        }

        response = await self._http2_client.post(
            url,
            headers={"Authorization": f"Bearer {self._get_bearer_token()}"},
            files=files,
            timeout=httpx.Timeout(30),
        )
        _LOGGER.debug(
            "AVS response [status %s]: %s", response.status_code, response.text
        )

        if response.status_code == HTTPStatus.NO_CONTENT:
            # If the AVS site is correct, we should get an empty response
            return

        _LOGGER.debug("Attempting to extract AVS site from response body")

        boundary = http2_parse_boundary_delimiter(
            response.headers.get("content-type", "")
        )
        if boundary is None:
            _LOGGER.warning("Missing multipart boundary in SynchronizeState response")
            return

        parser = AvsDirectiveStreamParser(boundary)
        parts = parser.feed(response.content)
        chunk_json = next(
            (http2_extract_json_from_part(p) for p in parts if p),
            None,
        )
        if chunk_json is None:
            _LOGGER.warning("Could not extract JSON from SynchronizeState response")
            return

        site = chunk_json.get("directive", {}).get("payload", {}).get("endpoint")
        if not site:
            _LOGGER.warning("Could not extract AVS site from SynchronizeState response")
            return

        self._avs_directive_site = site
        _LOGGER.debug("Updated AVS directive site: %s", site)
        raise UpdatedAVSSite

    async def _get_avs_directives(self) -> None:
        """Maintain AVS directive stream loop."""
        if not (await self._refresh_token()):
            return

        await self._stream_and_process()

    async def _refresh_token(self) -> bool:
        """Refresh the access token."""
        try:
            refresh_successful, _ = await self._http_wrapper.refresh_data(
                REFRESH_ACCESS_TOKEN
            )
            if not refresh_successful:
                _LOGGER.warning("Failed to refresh access token")
                return False
        except (CannotConnect, CannotRetrieveData) as exc:
            _LOGGER.warning("Failed to refresh access token: %s", exc)
            return False
        return True

    async def _stream_and_process(self) -> None:
        """Open stream and process incoming directives."""
        _LOGGER.debug("Starting AVS Directives stream")

        url = f"{self._avs_directive_site}/v{HTTP2_DIRECTIVES_VERSION}/directives"
        _LOGGER.debug("Connecting to AVS directives site %s", url)
        async with self._http2_client.stream(
            "GET",
            url,
            headers={
                "Authorization": f"Bearer {self._get_bearer_token()}",
                "Accept": "multipart/related",
                "Accept-Encoding": "gzip",
            },
            timeout=httpx.Timeout(None),
        ) as response:
            _LOGGER.debug(
                "AVS Directives response status: %s [%s]",
                response.status_code,
                response.http_version,
            )

            if response.status_code in (
                HTTPStatus.FORBIDDEN,
                HTTPStatus.PROXY_AUTHENTICATION_REQUIRED,
                HTTPStatus.UNAUTHORIZED,
            ):
                raise CannotAuthenticate(
                    f"Directives stream returned {response.status_code}"
                )

            boundary = http2_parse_boundary_delimiter(
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
            except UpdatedAVSSite:
                # Restarting with the correct AVS site
                return
            except BufferError:
                _LOGGER.error("Buffer exceeded maximum size, forcing reconnect")
                return
            finally:
                _LOGGER.debug("AVS Directives stream closed")
                self._connected_event.clear()

    async def _handle_part(self, part: bytes) -> None:
        """Process a single multipart section."""
        if not part:
            _LOGGER.debug("Empty part, check AVS site.")
            await self._check_avs_site()
            return

        chunk_json = http2_extract_json_from_part(part)
        if chunk_json is None:
            return

        rendering_updates = _extract_rendering_updates(chunk_json)
        if rendering_updates is None:
            return

        # All observed messages only contain one update but it is presented
        # as an array so iterate over all results in case that ever changes.
        for rendering_update in rendering_updates:
            result = _process_rendering_update(rendering_update)
            if result is None:
                _LOGGER.debug(
                    "Failed to process rendering update: %s", rendering_update
                )
                continue
            push_event_type, payload = result
            try:
                await self.on_push_event.send(push_event_type, payload)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Error processing push event type <%s>: %s",
                    push_event_type,
                    payload,
                )

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
                raise
            except httpx.TimeoutException:
                _LOGGER.warning("HTTP2: Ping timeout, forcing reconnect")
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.exception("HTTP2: Ping error (will retry)")

    async def _ping(self) -> None:
        """POST a keepalive to the AVS /ping endpoint."""
        if self._http2_client.is_closed:
            return

        response = await self._http2_client.post(
            f"{self._avs_directive_site}/ping",
            headers={"Authorization": f"Bearer {self._get_bearer_token()}"},
            timeout=httpx.Timeout(30),
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

        # Reset backoff after healthy ping
        self._reconnect_attempt = 0

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
